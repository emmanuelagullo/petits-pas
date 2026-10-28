#!/usr/bin/env python3
"""Mesurer PetitsPas.app : version minimale de macOS exigée et dépendances hors du système et du bundle.

Échoue si une dépendance pointe hors du système et du bundle (le .app ne se suffirait pas à lui-même) ou
si la version minimale mesurée dépasse celle annoncée aux utilisateurs sur le site (--annonce).
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

MAGIES_MACH_O = (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")


def binaires_mach_o(dossier):
    trouves = []
    for chemin in sorted(Path(dossier).rglob("*")):
        if chemin.is_file() and not chemin.is_symlink():
            with chemin.open("rb") as fichier:
                if fichier.read(4) in MAGIES_MACH_O:
                    trouves.append(chemin)
    return trouves


def dependances_hors_systeme(fichier, executer=subprocess.run):
    sortie = executer(["otool", "-L", str(fichier)], check=True, capture_output=True, text=True).stdout
    chemins = [ligne.strip().split(" (")[0] for ligne in sortie.splitlines()[1:] if ligne.strip()]
    return [c for c in chemins if not c.startswith(("/usr/lib/", "/System/Library/", "@"))]


def version_minimale(fichier, executer=subprocess.run):
    """Plus haute version minimale de macOS exigée par un Mach-O, en tuple (ex. (15, 0))."""
    sortie = executer(["otool", "-l", str(fichier)], check=True, capture_output=True, text=True).stdout
    versions, attente = [], None
    for ligne in sortie.splitlines():
        mots = ligne.split()
        if len(mots) == 2 and mots[0] == "cmd":
            attente = {"LC_BUILD_VERSION": "minos", "LC_VERSION_MIN_MACOSX": "version"}.get(mots[1])
        elif attente and len(mots) == 2 and mots[0] == attente:
            versions.append(tuple(int(x) for x in mots[1].split(".") if x.isdigit()))
            attente = None
    return max(versions, default=(0,))


def texte_version(version):
    return ".".join(str(x) for x in version)


def normalisee(version):
    """(15,) et (15, 0) désignent la même version : compléter à trois composantes avant de comparer."""
    return (tuple(version) + (0, 0, 0))[:3]


def mesurer(application, annonce, executer=subprocess.run):
    """Retourne (code, lignes de compte rendu) : 0 conforme, 1 écart, 2 rien à mesurer."""
    fichiers = binaires_mach_o(application)
    if not fichiers:
        return 2, [f"Aucun fichier Mach-O sous {application} : construire le .app d'abord."]
    externes = {}
    exigences = []
    for fichier in fichiers:
        deps = dependances_hors_systeme(fichier, executer)
        if deps:
            externes[fichier.name] = deps
        exigences.append((version_minimale(fichier, executer), fichier.name))
    exigences.sort(reverse=True)
    maximum, responsable = exigences[0]
    lignes = [f"{len(fichiers)} fichiers Mach-O mesurés.",
              f"Version minimale de macOS exigée par le bundle : {texte_version(maximum)}, imposée par {responsable}.",
              f"Version annoncée sur le site : macOS {texte_version(annonce)} ou plus récent."]
    code = 0
    if externes:
        nom, deps = next(iter(externes.items()))
        lignes.append(f"ÉCART : {len(externes)} fichier(s) dépendent d'un chemin externe, par exemple {nom} : {deps[0]}")
        code = 1
    if normalisee(maximum) > normalisee(annonce):
        lignes.append(f"ÉCART : le bundle exige macOS {texte_version(maximum)}, plus que la version annoncée : "
                      "corriger les pages d'installation avant de publier.")
        code = 1
    return code, lignes


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--application", type=Path, default=Path("dist/PetitsPas.app"))
    analyseur.add_argument("--annonce", default="15", help="Version de macOS annoncée aux utilisateurs.")
    arguments = analyseur.parse_args()
    annonce = tuple(int(x) for x in arguments.annonce.split("."))
    code, lignes = mesurer(arguments.application, annonce)
    texte = "\n".join(lignes)
    print(texte)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as sortie:
            sortie.write("## Mesure du bundle macOS\n\n" + "\n\n".join(lignes) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
