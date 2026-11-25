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


PREFIXE = "sha256:"


def empreinte_png(donnees):
    from hashlib import sha256

    return sha256(donnees).hexdigest()


def references_png(objet):
    if isinstance(objet, dict):
        valeur = objet.get("icone_png")
        if isinstance(valeur, str) and valeur.startswith(PREFIXE):
            yield valeur[len(PREFIXE):]
        for valeur in objet.values():
            yield from references_png(valeur)
    elif isinstance(objet, list):
        for valeur in objet:
            yield from references_png(valeur)


def conserver_png(objet, modele):
    if isinstance(objet, dict):
        valeur = objet.get("icone_png")
        if valeur and not valeur.startswith(PREFIXE):
            donnees = b64decode(valeur)
            empreinte = empreinte_png(donnees)
            modele.objects.get_or_create(empreinte=empreinte, defaults={"png": donnees})
            objet["icone_png"] = PREFIXE + empreinte
        for valeur in objet.values():
            conserver_png(valeur, modele)
    elif isinstance(objet, list):
        for valeur in objet:
            conserver_png(valeur, modele)


def png_en_ligne(valeur):
    if not valeur or not valeur.startswith(PREFIXE):
        return valeur
    from .models import IconePartagee

    donnees = IconePartagee.objects.filter(empreinte=valeur[len(PREFIXE):]).values_list("png", flat=True).first()
    if donnees is None:
        raise ValidationError("Une icône référencée est introuvable.")
    return b64encode(donnees).decode("ascii")


# Les projections et les instantanés référencent les mêmes octets que l’édition.
CHAMPS_PNG = {
    "VersionReferentiel": ("contenu",),
    "VersionSourceEcole": ("contenu",),
    "AdoptionReferentiel": ("contenu", "etat_final"),
    "AdaptationCompetence": ("ajout",),
}


def selection_icones(selection):
    empreintes = set()
    for modele, filtre in selection.items():
        champs = CHAMPS_PNG.get(modele.__name__)
        if champs:
            for valeurs in modele.objects.filter(filtre).values_list(*champs).iterator():
                for valeur in valeurs:
                    empreintes.update(references_png(valeur))
    return empreintes


def externaliser_png(document):
    """Remplace les PNG par leurs empreintes et retourne les octets uniques."""
    from .identites_referentiels import competences_document

    ressources = {}
    for competence in competences_document(document):
        valeur = competence.get("icone_png")
        if valeur:
            donnees = decoder_icone(png_en_ligne(valeur))
            empreinte = empreinte_png(donnees)
            ressources.setdefault(empreinte, donnees)
            competence["icone_png"] = PREFIXE + empreinte
    return ressources
