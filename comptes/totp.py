"""TOTP (RFC 6238) : clé chiffrée en base, vérification sans rejeu, QR.

django-otp ne sert qu'au calcul (django_otp.oath) : la clé étant chiffrée,
son modèle de dispositif ne convient pas. Les importations de cryptography,
qrcode et django_otp sont paresseuses : sans requirements-2fa.txt, ce module
s'importe quand même et la fonction reste simplement indisponible.
"""
import base64
import hashlib
import logging
import secrets
from io import BytesIO
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CodeSecoursDoubleFacteur, DoubleFacteurCompte

logger = logging.getLogger(__name__)

PAS = 30
CHIFFRES = 6
# Plus ou moins un pas : absorbe une dérive d'horloge raisonnable.
TOLERANCE = 1
OCTETS_CLE = 20


def _fernet():
    from cryptography.fernet import Fernet, MultiFernet

    return MultiFernet([Fernet(cle) for cle in settings.DOUBLE_FACTEUR_CLES])


def chiffrer(cle):
    return _fernet().encrypt(cle).decode()


def dechiffrer(jeton):
    return _fernet().decrypt(jeton.encode())


def cle_en_base32(cle):
    return base64.b32encode(cle).decode().rstrip("=")


def uri_otpauth(utilisateur, cle):
    emetteur = settings.DOUBLE_FACTEUR_EMETTEUR
    libelle = quote(f"{emetteur}:{utilisateur.get_username()}")
    return (
        f"otpauth://totp/{libelle}?secret={cle_en_base32(cle)}"
        f"&issuer={quote(emetteur)}&algorithm=SHA1&digits={CHIFFRES}&period={PAS}"
    )


def qr_svg(uri):
    """QR code en SVG, sans Pillow ; la déclaration XML est retirée pour
    pouvoir l'inclure directement dans une page HTML."""
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    sortie = BytesIO()
    image.save(sortie)
    svg = sortie.getvalue().decode()
    return svg[svg.index("<svg"):]


def _normaliser(code):
    chiffres = "".join(str(code).split())
    if len(chiffres) != CHIFFRES or not chiffres.isascii() or not chiffres.isdigit():
        return None
    return int(chiffres)


def _verifier_verrouille(compte, code, instant):
    """Vérifie un code sur une ligne déjà verrouillée ; refuse un pas déjà utilisé."""
    from cryptography.fernet import InvalidToken
    from django_otp.oath import TOTP

    jeton = _normaliser(code)
    if jeton is None or not compte.cle_chiffree:
        return False
    try:
        cle = dechiffrer(compte.cle_chiffree)
    except InvalidToken:
        logger.error(
            "Clé 2FA illisible pour le compte %s : la clé de chiffrement a-t-elle changé ?",
            compte.utilisateur_id,
        )
        return False
    totp = TOTP(cle, step=PAS, digits=CHIFFRES)
    if instant is not None:
        totp.time = instant
    if not totp.verify(jeton, tolerance=TOLERANCE, min_t=compte.dernier_pas + 1):
        return False
    compte.dernier_pas = totp.t()
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
        if not compte.cle_chiffree:
            compte.cle_chiffree = chiffrer(secrets.token_bytes(OCTETS_CLE))
            compte.save(update_fields=["cle_chiffree"])
    return compte


def cle_en_cours(compte):
    """Clé d'une inscription non confirmée, pour l'afficher une seule fois."""
    if compte.inscrit:
        raise ValidationError("La clé d'un compte déjà inscrit ne s'affiche plus.")
    return dechiffrer(compte.cle_chiffree)


def verifier_code(utilisateur, code, *, instant=None):
    """Vérifie un code d'un compte inscrit ; chaque pas ne sert qu'une fois."""
    with transaction.atomic():
        compte = DoubleFacteurCompte.objects.select_for_update().filter(
            utilisateur=utilisateur, confirme_le__isnull=False).first()
        if compte is None or not _verifier_verrouille(compte, code, instant):
            return False
        compte.save(update_fields=["dernier_pas"])
        return True


def confirmer_inscription(utilisateur, code, *, instant=None):
    """Confirme l'inscription par un premier code valide ; retire l'échéance."""
    with transaction.atomic():
        compte = DoubleFacteurCompte.objects.select_for_update().filter(
            utilisateur=utilisateur, confirme_le__isnull=True).exclude(cle_chiffree="").first()
        if compte is None or not _verifier_verrouille(compte, code, instant):
            return False
        compte.confirme_le = timezone.now()
        compte.echeance_le = None
        compte.save(update_fields=["dernier_pas", "confirme_le", "echeance_le"])
        return True


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
ALPHABET_SECOURS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE_SECOURS = 16
NOMBRE_CODES_SECOURS = 10


def _empreinte(code_normalise):
    return hashlib.sha256(code_normalise.encode()).hexdigest()


def normaliser_code_secours(saisie):
    """Majuscules, sans espaces ni tirets ; None si la forme est impossible."""
    code = "".join(c for c in str(saisie or "").upper() if c not in " -")
    if len(code) != LONGUEUR_CODE_SECOURS or any(c not in ALPHABET_SECOURS for c in code):
        return None
    return code


def presenter_code_secours(code):
    return "-".join(code[i:i + 4] for i in range(0, LONGUEUR_CODE_SECOURS, 4))


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
            code = "".join(secrets.choice(ALPHABET_SECOURS) for _ in range(LONGUEUR_CODE_SECOURS))
            if code not in codes:
                codes.append(code)
        CodeSecoursDoubleFacteur.objects.bulk_create(
            CodeSecoursDoubleFacteur(utilisateur=utilisateur, empreinte=_empreinte(code))
            for code in codes)
    return [presenter_code_secours(code) for code in codes]


def utiliser_code_secours(utilisateur, saisie):
    """Consomme un code de secours ; chaque code ne sert qu'une fois."""
    code = normaliser_code_secours(saisie)
    if code is None or not est_inscrit(utilisateur):
        return False
    return bool(CodeSecoursDoubleFacteur.objects.filter(
        utilisateur=utilisateur, empreinte=_empreinte(code), utilise_le__isnull=True,
    ).update(utilise_le=timezone.now()))


def codes_secours_restants(utilisateur):
    return CodeSecoursDoubleFacteur.objects.filter(
        utilisateur=utilisateur, utilise_le__isnull=True).count()
