"""Noms publics des téléchargements Petits Pas, indépendants du contenu des ZIP."""
import re

from django.utils import timezone
from django.utils.text import slugify


def _segment(valeur, limite=36):
    return slugify(str(valeur or "").replace("_", "-").replace(".", "-"))[:limite].strip("-")


def nom_zip(type_archive, *sujets, edition=None, date=None):
    type_normalise = _segment(type_archive) or "archive"
    elements = ["petits-pas", type_normalise]
    elements.extend(segment for sujet in sujets if (segment := _segment(sujet)))
    if edition:
        elements.extend(("edition", _segment(edition) or "sans-numero"))
    if date is not None or not edition:
        elements.append(f"{date or timezone.now():%Y-%m-%d-%H%M%S}")
    return "-".join(elements) + ".zip"



def enregistrer_nom_zip(dossier, nom):
    (dossier / "nom-telechargement").write_text(nom, encoding="ascii")


def relire_nom_zip(dossier, secours):
    try:
        nom = (dossier / "nom-telechargement").read_text(encoding="ascii")
    except (FileNotFoundError, UnicodeError):
        return secours
    return nom if re.fullmatch(r"petits-pas-[a-z0-9-]{1,210}\.zip", nom) else secours
