"""Adaptation du traitement d'images aux fichiers attendus par Django."""

from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

from .medias import normaliser_image


def preparer_image(source, *, famille="trace"):
    image = normaliser_image(source, famille=famille)
    nom_source = Path(getattr(source, "name", "image")).stem
    nom = slugify(nom_source) or "image"
    return ContentFile(image.contenu, name=f"{nom}.jpg")
