#!/usr/bin/env python3
"""Valide les illustrations publiques référencées par Petits Pas."""

from pathlib import Path, PurePosixPath
import re
import sys
from xml.etree import ElementTree

from PIL import Image, UnidentifiedImageError
import yaml


RACINE = Path(__file__).resolve().parents[1]
STATIQUES = (RACINE / "referentiel" / "static").resolve()
CATALOGUE = RACINE / "referentiel" / "icones.yaml"
EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
NOM_SUR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def erreur(message):
    raise ValueError(message)


def chemin_catalogue(valeur):
    relatif = PurePosixPath(valeur)
    if relatif.is_absolute() or ".." in relatif.parts:
        erreur(f"Chemin statique non sûr : {valeur}")
    if relatif.suffix.lower() not in EXTENSIONS:
        erreur(f"Format statique non admis : {valeur}")
    if any(not NOM_SUR.fullmatch(part) for part in relatif.parts):
        erreur(f"Nom de fichier non portable : {valeur}")
    chemin = (STATIQUES / Path(*relatif.parts)).resolve()
    if STATIQUES not in chemin.parents or not chemin.is_file():
        erreur(f"Illustration statique introuvable : {valeur}")
    return chemin


def valider_svg(chemin):
    if chemin.stat().st_size > 100_000:
        erreur(f"SVG trop lourd (100 ko maximum) : {chemin.relative_to(RACINE)}")
    try:
        racine = ElementTree.parse(chemin).getroot()
    except ElementTree.ParseError as exc:
        erreur(f"SVG invalide : {chemin.relative_to(RACINE)} ({exc})")
    if racine.tag.rsplit("}", 1)[-1] != "svg":
        erreur(f"Racine SVG absente : {chemin.relative_to(RACINE)}")
    if not (racine.get("viewBox") or (racine.get("width") and racine.get("height"))):
        erreur(f"Dimensions SVG absentes : {chemin.relative_to(RACINE)}")
    for element in racine.iter():
        if element.tag.rsplit("}", 1)[-1] == "script":
            erreur(f"Script interdit dans un SVG : {chemin.relative_to(RACINE)}")
        for nom, valeur in element.attrib.items():
            if nom.rsplit("}", 1)[-1] == "href" and valeur.strip().lower().startswith(
                ("http:", "https:", "data:", "//")
            ):
                erreur(f"Ressource externe interdite dans un SVG : {chemin.relative_to(RACINE)}")


def valider_raster(chemin):
    if chemin.stat().st_size > 500_000:
        erreur(f"Illustration trop lourde (500 ko maximum) : {chemin.relative_to(RACINE)}")
    try:
        with Image.open(chemin) as image:
            image.verify()
        with Image.open(chemin) as image:
            if max(image.size) > 1600:
                erreur(f"Illustration trop grande (1 600 px maximum) : {chemin.relative_to(RACINE)}")
            if image.getexif():
                erreur(f"Métadonnées EXIF interdites : {chemin.relative_to(RACINE)}")
    except (UnidentifiedImageError, OSError) as exc:
        erreur(f"Illustration illisible : {chemin.relative_to(RACINE)} ({exc})")


def valider():
    donnees = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8")) or {}
    icones = donnees.get("icones") or {}
    if not isinstance(icones, dict):
        erreur("Le catalogue icones.yaml doit contenir une table 'icones'.")
    chemins = set()
    for identifiant, entree in icones.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifiant):
            erreur(f"Identifiant d'icône invalide : {identifiant}")
        valeur = (entree or {}).get("fichier", "")
        chemin = chemin_catalogue(valeur)
        if chemin in chemins:
            erreur(f"Illustration déclarée deux fois : {valeur}")
        chemins.add(chemin)
        valider_svg(chemin) if chemin.suffix.lower() == ".svg" else valider_raster(chemin)
    return len(chemins)


if __name__ == "__main__":
    try:
        nombre = valider()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
    print(f"Illustrations statiques validées : {nombre}")
