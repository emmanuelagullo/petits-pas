"""Stockage et consommation TOTP Petits Pas ; primitives dans Pas communs.

Les modèles, transactions et échéances restent dans comptes. Les dépendances
crypto sont paresseuses et les parcours/politiques restent dans suivi.
"""
import logging
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from pas_communs.authentification import totp as moteur

from .models import CodeSecoursDoubleFacteur, DoubleFacteurCompte

logger = logging.getLogger(__name__)

PAS = moteur.PAS
CHIFFRES = moteur.CHIFFRES
# Plus ou moins un pas : absorbe une dérive d'horloge raisonnable.
TOLERANCE = moteur.TOLERANCE
OCTETS_CLE = moteur.OCTETS_CLE


def chiffrer(cle):
    return moteur.chiffrer(cle, cles=settings.DOUBLE_FACTEUR_CLES)


def dechiffrer(jeton):
    return moteur.dechiffrer(jeton, cles=settings.DOUBLE_FACTEUR_CLES)


cle_en_base32 = moteur.cle_en_base32
qr_svg = moteur.qr_svg


def uri_otpauth(utilisateur, cle):
    return moteur.uri_otpauth(utilisateur.get_username(), cle,
        emetteur=settings.DOUBLE_FACTEUR_EMETTEUR)


def _verifier_verrouille(compte, code, instant):
    """Vérifie un code sur une ligne déjà verrouillée ; refuse un pas déjà utilisé."""
    from cryptography.fernet import InvalidToken

    if not compte.cle_chiffree:
        return False
    try:
        cle = dechiffrer(compte.cle_chiffree)
    except InvalidToken:
        logger.error(
            "Clé 2FA illisible pour le compte %s : la clé de chiffrement a-t-elle changé ?",
            compte.utilisateur_id,
        )
        return False
    pas = moteur.verifier_pas(cle, code, dernier_pas=compte.dernier_pas, instant=instant)
    if pas is None:
        return False
    compte.dernier_pas = pas
    return True


def est_inscrit(utilisateur):
    return DoubleFacteurCompte.objects.filter(
        utilisateur=utilisateur, confirme_le__isnull=False
    ).exclude(cle_chiffree="").exists()


def commencer_inscription(utilisateur):
    """Génère (ou reprend) la clé d'une inscription non confirmée.

    Une même clé est reprise tant qu'elle n'est pas confirmée : recharger la
    page ne change pas le code à scanner.
    """
    with transaction.atomic():
        DoubleFacteurCompte.objects.get_or_create(utilisateur=utilisateur)
        compte = DoubleFacteurCompte.objects.select_for_update().get(utilisateur=utilisateur)
        if compte.inscrit:
            raise ValidationError("Le second facteur est déjà configuré pour ce compte.")
        if compte.cle_chiffree and not _cle_lisible(compte.cle_chiffree):
            # Clé de chiffrement changée sans conserver l'ancienne pendant une
            # inscription non confirmée : rien n'est encore protégé, on repart.
            logger.warning("Clé d'inscription illisible : régénérée (compte %s)", utilisateur.pk)
            compte.cle_chiffree = ""
        if not compte.cle_chiffree:
            compte.cle_chiffree = chiffrer(secrets.token_bytes(OCTETS_CLE))
            compte.save(update_fields=["cle_chiffree"])
    return compte


def _cle_lisible(jeton):
    from cryptography.fernet import InvalidToken

    try:
        dechiffrer(jeton)
    except InvalidToken:
        return False
    return True


def cle_en_cours(compte):
    """Clé d'une inscription non confirmée, pour l'afficher une seule fois."""
    if compte.inscrit:
        raise ValidationError("La clé d'un compte déjà inscrit ne s'affiche plus.")
    return dechiffrer(compte.cle_chiffree)


def verifier_code(utilisateur, code, *, instant=None):
    """Vérifie un code d'un compte inscrit ; chaque pas ne sert qu'une fois."""
    try:
        compte = DoubleFacteurCompte.objects.filter(
            utilisateur=utilisateur, confirme_le__isnull=False).first()
        ancien_pas = compte.dernier_pas if compte else None
        if compte is None or not _verifier_verrouille(compte, code, instant):
            return False
        # Une instruction compare-et-échange : SQLite n'a pas de verrou de ligne.
        # La clé et la confirmation lient le calcul à l'inscription encore active.
        return bool(DoubleFacteurCompte.objects.filter(pk=compte.pk,
            cle_chiffree=compte.cle_chiffree, confirme_le=compte.confirme_le,
            dernier_pas=ancien_pas).update(dernier_pas=compte.dernier_pas))
    except DatabaseError:
        logger.warning("Vérification 2FA refusée : stockage indisponible.")
        return False


def confirmer_inscription(utilisateur, code, *, instant=None):
    """Confirme l'inscription par un premier code valide ; retire l'échéance."""
    try:
        compte = DoubleFacteurCompte.objects.filter(
            utilisateur=utilisateur, confirme_le__isnull=True).exclude(cle_chiffree="").first()
        ancien_pas = compte.dernier_pas if compte else None
        if compte is None or not _verifier_verrouille(compte, code, instant):
            return False
        return bool(DoubleFacteurCompte.objects.filter(pk=compte.pk,
            cle_chiffree=compte.cle_chiffree, confirme_le__isnull=True,
            dernier_pas=ancien_pas).update(dernier_pas=compte.dernier_pas,
                confirme_le=timezone.now(), echeance_le=None))
    except DatabaseError:
        logger.warning("Confirmation 2FA refusée : stockage indisponible.")
        return False


def retirer(utilisateur):
    CodeSecoursDoubleFacteur.objects.filter(utilisateur=utilisateur).delete()
    DoubleFacteurCompte.objects.filter(utilisateur=utilisateur).delete()


def reinitialiser(utilisateur):
    """Efface le second facteur et les codes de secours d'un compte.

    La ligne reste (avec son échéance éventuelle) : le compte n'est plus
    inscrit et devra se réinscrire, sans que l'obligation disparaisse.
    """
    with transaction.atomic():
        CodeSecoursDoubleFacteur.objects.filter(utilisateur=utilisateur).delete()
        DoubleFacteurCompte.objects.filter(utilisateur=utilisateur).update(
            cle_chiffree="", confirme_le=None, dernier_pas=0)


# --- Codes de secours -------------------------------------------------------
# Seize caractères d'un alphabet de 32 sans ambiguïté (80 bits) : assez pour
# qu'une simple empreinte SHA-256 résiste à une fuite de la base.
ALPHABET_SECOURS = moteur.ALPHABET_SECOURS
LONGUEUR_CODE_SECOURS = moteur.LONGUEUR_CODE_SECOURS
NOMBRE_CODES_SECOURS = moteur.NOMBRE_CODES_SECOURS
_empreinte = moteur.empreinte_code_secours
normaliser_code_secours = moteur.normaliser_code_secours
presenter_code_secours = moteur.presenter_code_secours


def generer_codes_secours(utilisateur):
    """Remplace les codes d'un compte inscrit ; retourne les nouveaux, en clair,
    pour un affichage unique : seules leurs empreintes sont conservées."""
    with transaction.atomic():
        if not DoubleFacteurCompte.objects.select_for_update().filter(
                utilisateur=utilisateur, confirme_le__isnull=False).exists():
            raise ValidationError("Le second facteur n'est pas configuré pour ce compte.")
        CodeSecoursDoubleFacteur.objects.filter(utilisateur=utilisateur).delete()
        codes = []
        while len(codes) < NOMBRE_CODES_SECOURS:
            code = moteur.nouveau_code_secours()
            if code not in codes:
                codes.append(code)
        CodeSecoursDoubleFacteur.objects.bulk_create(
            CodeSecoursDoubleFacteur(utilisateur=utilisateur, empreinte=_empreinte(code))
            for code in codes)
    return [presenter_code_secours(code) for code in codes]


def utiliser_code_secours(utilisateur, saisie):
    """Consomme un code de secours ; chaque code ne sert qu'une fois."""
    code = normaliser_code_secours(saisie)
    if code is None:
        return False
    try:
        compte = DoubleFacteurCompte.objects.filter(utilisateur=utilisateur,
            confirme_le__isnull=False).exclude(cle_chiffree='').first()
        if compte is None:
            return False
        return bool(CodeSecoursDoubleFacteur.objects.filter(
            utilisateur=utilisateur, empreinte=_empreinte(code), utilise_le__isnull=True,
            utilisateur__double_facteur__cle_chiffree=compte.cle_chiffree,
            utilisateur__double_facteur__confirme_le=compte.confirme_le,
        ).update(utilise_le=timezone.now()))
    except DatabaseError:
        logger.warning("Code de secours refusé : stockage indisponible.")
        return False


def codes_secours_restants(utilisateur):
    return CodeSecoursDoubleFacteur.objects.filter(
        utilisateur=utilisateur, utilise_le__isnull=True).count()
