"""Adaptation du traitement d'images aux fichiers attendus par Django."""

from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

from .medias import normaliser_variantes


def preparer_variantes(source, *, famille="trace"):
    variantes = normaliser_variantes(source, famille=famille)
    nom_source = Path(getattr(source, "name", "image")).stem
    nom = slugify(nom_source) or "image"
    principale = ContentFile(
        variantes.principale.contenu,
        name=f"{nom}.jpg",
    )
    pdf = ContentFile(
        variantes.pdf.contenu,
        name=f"{nom}-pdf.jpg",
    )
    return principale, pdf
