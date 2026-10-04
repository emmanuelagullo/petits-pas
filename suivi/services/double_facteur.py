"""Politique de 2FA de l'école : lecture et enregistrement par la direction."""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from carnet.double_facteur import verifier_curseurs
from suivi.audit import journaliser
from suivi.autorisations import ADMINISTRER_ECOLE, autorise
from suivi.double_facteur import combiner, politique_deployeur
from suivi.models import Ecole, PolitiqueDoubleFacteurEcole


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
