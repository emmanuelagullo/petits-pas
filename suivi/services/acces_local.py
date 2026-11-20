"""Accès sur l'appareil de l'école : clé de secours, dernier recours, liens.

Rien ici ne s'ouvre hors du profil local déclaré par le lanceur
(`settings.ACCES_LOCAL_AUTONOME`). La clé de secours reprend les primitives du
second facteur ; le dernier recours est un choix de l'école (case modifiable
par la direction) : avoir l'appareil en main vaut alors autorité, puisque les
données de l'installation locale ne sont pas chiffrées.
"""
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from comptes import secours_local
from comptes.models import AppartenanceEcole, RecoursLocalEcole, Utilisateur
from suivi.acces_double_facteur import fermer_sessions_compte
from suivi.audit import journaliser
from suivi.autorisations import ADMINISTRER_ECOLE, appartenances_actives, autorise
from suivi.models import Ecole, EvenementAudit

from .double_facteur import journaliser_securite_compte

ACTION_REINITIALISE = "mot_de_passe_reinitialise"
MOYEN_CLE = "cle_de_secours"
MOYEN_DERNIER_RECOURS = "dernier_recours"


def disponible():
    return bool(settings.ACCES_LOCAL_AUTONOME)


def _exiger_disponible():
    if not disponible():
        raise PermissionDenied


def ecole_locale():
    """L'école de l'installation : une installation locale n'en a qu'une."""
    return Ecole.objects.order_by("pk").first()


def dernier_recours_autorise(ecole=None):
    if not disponible():
        return False
    ecole = ecole or ecole_locale()
    return bool(ecole and RecoursLocalEcole.objects.filter(
        ecole=ecole, dernier_recours=True).exists())


def definir_dernier_recours(*, acteur, ecole, autorise_recours):
    """Enregistre le choix de l'école ; réservé à la direction."""
    _exiger_disponible()
    if not autorise(acteur, ADMINISTRER_ECOLE, ecole=ecole):
        raise PermissionDenied
    with transaction.atomic():
        ligne, _ = RecoursLocalEcole.objects.get_or_create(ecole=ecole)
        ancien = ligne.dernier_recours
        ligne.dernier_recours = bool(autorise_recours)
        ligne.save()
        if ancien != ligne.dernier_recours:
            journaliser(acteur, "dernier_recours_local", ecole,
                        anciennes={"autorise": ancien},
                        nouvelles={"autorise": ligne.dernier_recours})
    return ligne


def comptes_reinitialisables(ecole):
    """Comptes actifs ayant une appartenance en cours à l'école, par nom."""
    identifiants = [a.utilisateur_id for a in AppartenanceEcole.objects.filter(ecole=ecole)
                    if a.est_active()]
    return list(Utilisateur.objects.filter(pk__in=identifiants, is_active=True)
                .order_by("last_name", "first_name", "username"))


def generer_cle(utilisateur):
    """Nouvelle clé de secours (l'ancienne cesse de valoir) ; à montrer une fois."""
    _exiger_disponible()
    cle = secours_local.creer_cle(utilisateur)
    journaliser_securite_compte(utilisateur, utilisateur, "cle_secours_creee")
    return cle


def _definir_mot_de_passe(compte, nouveau, moyen):
    validate_password(nouveau, compte)
    with transaction.atomic():
        compte.set_password(nouveau)
        compte.save(update_fields=["password"])
        fermer_sessions_compte(compte)
        journaliser_securite_compte(None, compte, ACTION_REINITIALISE, moyen=moyen)


def reinitialiser_par_cle(compte, nouveau_mot_de_passe):
    """Nouveau mot de passe d'un compte reconnu par sa clé ; retourne la clé suivante.

    La clé qui vient de servir est remplacée : elle a pu être vue par d'autres.
    """
    _exiger_disponible()
    _definir_mot_de_passe(compte, nouveau_mot_de_passe, MOYEN_CLE)
    return generer_cle(compte)


def reinitialiser_dernier_recours(compte, nouveau_mot_de_passe, ecole):
    """Nouveau mot de passe, sans autre preuve que d'avoir l'appareil en main."""
    _exiger_disponible()
    if not dernier_recours_autorise(ecole):
        raise PermissionDenied
    if compte not in comptes_reinitialisables(ecole):
        raise PermissionDenied
    _definir_mot_de_passe(compte, nouveau_mot_de_passe, MOYEN_DERNIER_RECOURS)


def refus_lien_reinitialisation(acteur, cible, ecole):
    """Motif pour lequel la direction ne peut pas obtenir de lien, ou None."""
    if not disponible():
        return "Cette fonction n'existe que sur l'appareil de l'école."
    if not autorise(acteur, ADMINISTRER_ECOLE, ecole=ecole):
        return "Seule la direction de l'école peut obtenir ce lien."
    if acteur.pk == cible.pk:
        return "Pour votre propre mot de passe, utilisez « Changer mon mot de passe »."
    if not appartenances_actives(cible).filter(ecole=ecole).exists():
        return "Cette personne n'est plus membre de l'école."
    return None


def lien_reinitialisation(*, acteur, cible, ecole, requete):
    """Lien d'un nouveau mot de passe pour un collègue, à lui transmettre en main propre."""
    motif = refus_lien_reinitialisation(acteur, cible, ecole)
    if motif:
        raise ValidationError(motif)
    jeton = default_token_generator.make_token(cible)
    uid = urlsafe_base64_encode(force_bytes(cible.pk))
    journaliser_securite_compte(acteur, cible, "lien_reinitialisation_emis")
    return requete.build_absolute_uri(
        reverse("mot_de_passe_reinitialiser", args=[uid, jeton]))


def reinitialisations_a_signaler(utilisateur, depuis):
    """Réinitialisations survenues depuis la dernière connexion de cette personne.

    Le dernier recours est signalé à la personne concernée et à la direction ;
    la réinitialisation par clé, seulement aux autres directions.
    """
    if depuis is None or not disponible():
        return []
    ecoles = [a.ecole for a in appartenances_actives(utilisateur).select_related("ecole")]
    resultat = []
    for ecole in ecoles:
        direction = autorise(utilisateur, ADMINISTRER_ECOLE, ecole=ecole)
        evenements = EvenementAudit.objects.filter(
            ecole=ecole, action=ACTION_REINITIALISE, cree_le__gt=depuis)
        for evenement in evenements:
            valeurs = evenement.nouvelles_valeurs
            cible_id = valeurs.get("cible_id")
            moyen = valeurs.get("moyen")
            concerne = cible_id == utilisateur.pk
            if moyen == MOYEN_DERNIER_RECOURS and not (concerne or direction):
                continue
            if moyen == MOYEN_CLE and not (direction and not concerne):
                continue
            cible = Utilisateur.objects.filter(pk=cible_id).first()
            resultat.append({
                "quand": evenement.cree_le,
                "nom": (cible.get_full_name() or cible.username) if cible else "?",
                "moi": concerne,
                "moyen": moyen,
            })
    return sorted(resultat, key=lambda e: e["quand"])
