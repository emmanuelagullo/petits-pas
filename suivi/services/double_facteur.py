"""Politique de 2FA de l'école : lecture et enregistrement par la direction."""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from carnet.double_facteur import DIRECTION, verifier_curseurs
from comptes import totp
from comptes.models import DoubleFacteurCompte
from suivi.acces_double_facteur import fermer_sessions_compte, poser_echeance_si_besoin
from suivi.audit import journaliser
from suivi.autorisations import ADMINISTRER_ECOLE, appartenances_actives, autorise
from suivi.double_facteur import combiner, politique_deployeur, rang_le_plus_haut
from suivi.models import Ecole, PolitiqueDoubleFacteurEcole

logger = logging.getLogger(__name__)


def lire_politique_ecole(*, utilisateur, ecole):
    """Valeurs de l'école, politique effective et révision à confirmer."""
    if not autorise(utilisateur, ADMINISTRER_ECOLE, ecole):
        raise PermissionDenied
    stockee = PolitiqueDoubleFacteurEcole.objects.filter(ecole=ecole).first()
    obligatoire = stockee.obligatoire_jusqu_au_rang if stockee else 0
    desactive = stockee.desactive_a_partir_du_rang if stockee else 6
    return {
        "obligatoire_jusqu_au_rang": obligatoire,
        "desactive_a_partir_du_rang": desactive,
        "revision": stockee.revision if stockee else 0,
        "deployeur": politique_deployeur(),
        "effective": combiner(politique_deployeur(), obligatoire, desactive),
    }


def _verifier_sous_le_deployeur(obligatoire, desactive):
    """Refuse une intention contraire au déployeur.

    Un curseur moins strict que le déployeur (obligation plus basse,
    désactivation plus haute) est accepté : il exprime « rien de plus » et
    reste sans effet. Cela évite qu'une valeur héritée soit recopiée comme un
    choix propre, qui subsisterait si le déployeur assouplissait ensuite.
    """
    deployeur = politique_deployeur()
    if obligatoire >= deployeur.desactive_a_partir_du_rang:
        raise ValidationError("L'école ne peut pas rendre obligatoire ce que le déployeur a désactivé.")
    if desactive <= deployeur.obligatoire_jusqu_au_rang:
        raise ValidationError("L'école ne peut pas désactiver ce que le déployeur a rendu obligatoire.")


@transaction.atomic
def enregistrer_politique_ecole(*, utilisateur, ecole, obligatoire_jusqu_au_rang,
                                desactive_a_partir_du_rang, revision_attendue):
    if not autorise(utilisateur, ADMINISTRER_ECOLE, ecole):
        raise PermissionDenied
    if not settings.DOUBLE_FACTEUR_DISPONIBLE:
        raise ValidationError("L'authentification à deux facteurs n'est pas disponible sur ce déploiement.")
    if type(revision_attendue) is not int or revision_attendue < 0:
        raise ValidationError("La révision attendue doit être un entier positif ou nul.")
    try:
        verifier_curseurs(obligatoire_jusqu_au_rang, desactive_a_partir_du_rang)
    except ValueError as erreur:
        raise ValidationError(str(erreur)) from erreur
    _verifier_sous_le_deployeur(obligatoire_jusqu_au_rang, desactive_a_partir_du_rang)
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    politique, _ = PolitiqueDoubleFacteurEcole.objects.get_or_create(ecole=ecole)
    politique = PolitiqueDoubleFacteurEcole.objects.select_for_update().get(pk=politique.pk)
    if politique.revision != revision_attendue:
        raise ValidationError("La politique a changé depuis sa consultation. Relisez-la avant de confirmer.")
    anciennes = {
        "obligatoire_jusqu_au_rang": politique.obligatoire_jusqu_au_rang,
        "desactive_a_partir_du_rang": politique.desactive_a_partir_du_rang,
        "revision": politique.revision,
    }
    politique.obligatoire_jusqu_au_rang = obligatoire_jusqu_au_rang
    politique.desactive_a_partir_du_rang = desactive_a_partir_du_rang
    politique.revision += 1
    politique.save(update_fields=[
        "obligatoire_jusqu_au_rang", "desactive_a_partir_du_rang", "revision"])
    journaliser(utilisateur, "securite.double_facteur_ecole", politique, anciennes=anciennes,
        nouvelles={"obligatoire_jusqu_au_rang": obligatoire_jusqu_au_rang,
                   "desactive_a_partir_du_rang": desactive_a_partir_du_rang,
                   "revision": politique.revision})
    return politique


def journaliser_securite_compte(acteur, cible, action, **valeurs):
    """Trace un événement de sécurité d'un compte dans chaque école où il est actif.

    Le journal d'audit est rattaché à une école : un compte sans appartenance
    active n'y laisse rien, mais l'événement reste dans les journaux du serveur.
    """
    logger.warning("%s : compte %s, par %s", action, cible.pk, acteur.pk if acteur else "?")
    for appartenance in appartenances_actives(cible).select_related("ecole"):
        journaliser(acteur or cible, action, appartenance,
                    nouvelles={"cible_id": cible.pk, **valeurs})


def _effacer_second_facteur(cible):
    """Efface clé et codes ; l'obligation, elle, demeure : si elle s'applique
    encore, la personne devra se réinscrire dès sa connexion suivante, sans
    nouveau délai de grâce."""
    totp.reinitialiser(cible)
    DoubleFacteurCompte.objects.filter(utilisateur=cible).update(echeance_le=None)
    poser_echeance_si_besoin(cible, delai_de_grace=False)
    # Une session ouverte avant la réinitialisation (appareil perdu ou volé)
    # ne doit pas pouvoir enrôler le nouvel authentificateur : la personne
    # se reconnecte, puis se réinscrit.
    fermer_sessions_compte(cible)


def refus_reinitialisation(acteur, cible, ecole):
    """Motif pour lequel la direction ne peut pas réinitialiser ce compte, ou None."""
    if not autorise(acteur, ADMINISTRER_ECOLE, ecole):
        return "Seule la direction de l'école peut réinitialiser le second facteur."
    if acteur.pk == cible.pk:
        return "Vous ne pouvez pas réinitialiser votre propre second facteur."
    if not appartenances_actives(cible).filter(ecole=ecole).exists():
        return "Cette personne n'est pas membre de l'école."
    if not totp.est_inscrit(cible):
        return "Cette personne n'a pas de second facteur à réinitialiser."
    if rang_le_plus_haut(cible) <= DIRECTION:
        # Comparé au plus haut rang du compte, toutes écoles confondues : une
        # direction ne peut pas affaiblir un compte qui est aussi direction
        # ailleurs. L'intervention est alors celle du déployeur.
        return ("Cette personne a une fonction de direction : seul le déployeur "
                "peut réinitialiser son second facteur.")
    return None


@transaction.atomic
def reinitialiser_par_la_direction(*, acteur, cible, ecole):
    if not settings.DOUBLE_FACTEUR_DISPONIBLE:
        raise ValidationError("L'authentification à deux facteurs n'est pas disponible sur ce déploiement.")
    motif = refus_reinitialisation(acteur, cible, ecole)
    if motif:
        if not autorise(acteur, ADMINISTRER_ECOLE, ecole):
            raise PermissionDenied
        raise ValidationError(motif)
    _effacer_second_facteur(cible)
    appartenance = appartenances_actives(cible).filter(ecole=ecole).first()
    journaliser(acteur, "securite.double_facteur_reinitialise", appartenance,
                nouvelles={"cible_id": cible.pk, "par": "direction"})
    logger.warning("Second facteur réinitialisé : compte %s, par la direction %s", cible.pk, acteur.pk)


@transaction.atomic
def reinitialiser_par_le_deployeur(*, operateur, cible, motif):
    """Intervention du déployeur (commande) : tous les comptes, direction comprise."""
    if not operateur.is_active or not operateur.is_staff:
        raise PermissionDenied
    _effacer_second_facteur(cible)
    journaliser_securite_compte(
        operateur, cible, "securite.double_facteur_reinitialise", par="deployeur", motif=motif)
