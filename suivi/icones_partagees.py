"""Validation des petites icônes matricielles des référentiels."""
from base64 import b64decode, b64encode
from binascii import Error
from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_PNG = 256 * 1024
MAX_COTE = 256


def verifier_png(donnees):
    try:
        if len(donnees) > MAX_PNG:
            raise ValueError
        with Image.open(BytesIO(donnees), formats=["PNG"]) as image:
            if max(image.size) > MAX_COTE or getattr(image, "is_animated", False):
                raise ValueError
            image.verify()
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError, UnidentifiedImageError) as erreur:
        raise ValidationError("Choisissez une icône PNG fixe de 256 × 256 pixels et 256 Kio au maximum.") from erreur


def encoder_icone(donnees):
    verifier_png(donnees)
    # Reconstruire l’image à partir des pixels pour écarter les métadonnées.
    with Image.open(BytesIO(donnees), formats=["PNG"]) as image:
        sortie = BytesIO()
        try:
            image.convert("RGBA").save(sortie, format="PNG", optimize=True)
        except OSError as erreur:
            raise ValidationError("Impossible de lire les pixels de l’icône.") from erreur
    donnees = sortie.getvalue()
    verifier_png(donnees)
    return b64encode(donnees).decode("ascii")


def decoder_icone(valeur):
    try:
        if not isinstance(valeur, str) or len(valeur) > 4 * ((MAX_PNG + 2) // 3):
            raise ValueError
        donnees = b64decode(valeur, validate=True)
    except (Error, ValueError) as erreur:
        raise ValidationError("L’icône PNG du référentiel est invalide.") from erreur
    verifier_png(donnees)
    return donnees
