#!/usr/bin/env python3
"""Vérifie la structure, les liens et les captures du guide pratique."""

import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from suivi.configuration_demo import charger_configuration_demo

CONTENU = RACINE / "site" / "content"
GUIDE = CONTENU / "guide"
DONNEES_GUIDE = RACINE / "site" / "data" / "guide.yaml"
DONNEES_DEMONSTRATION = RACINE / "site" / "data" / "demonstration.yaml"

CHAMPS_FICHE = {
    "title",
    "description",
    "categorie",
    "publics",
    "intentions",
    "prerequis",
    "depart",
    "statut",
}
CAPTURES_GENERALES = {
    "captures/connexion.png",
    "captures/classe.png",
    "captures/acquisitions.png",
    "captures/carnet.png",
    "captures/direction.png",
}


def lire_entete(chemin):
    texte = chemin.read_text(encoding="utf-8")
    if not texte.startswith("+++\n"):
        return {}, texte
    try:
        entete, corps = texte[4:].split("\n+++\n", 1)
    except ValueError as erreur:
        raise RuntimeError(f"{chemin} : en-tête TOML non terminé.") from erreur
    try:
        return tomllib.loads(entete), corps
    except tomllib.TOMLDecodeError as erreur:
        raise RuntimeError(f"{chemin} : en-tête TOML invalide : {erreur}") from erreur


def resoudre_contenu(page, cible):
    cible = unquote(urlsplit(cible).path)
    if cible.startswith("/"):
        base = CONTENU / cible.lstrip("/")
    else:
        base = page.parent / cible
    candidats = [base]
    if base.suffix not in {".md", ".org"}:
        candidats.extend((base.with_suffix(".md"), base / "_index.md"))
    return next((candidat for candidat in candidats if candidat.is_file()), None)


def verifier_liens(page, corps, erreurs):
    cibles_relref = re.findall(r'{{<\s*relref\s+"([^"]+)"\s*>}}', corps)
    for cible in cibles_relref:
        if resoudre_contenu(page, cible) is None:
            erreurs.append(f"{page} : cible relref introuvable : {cible}")

    for cible in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", corps):
        cible = cible.strip()
        if (
            not cible
            or cible.startswith(("{{<", "#", "mailto:"))
            or urlsplit(cible).scheme
        ):
            continue
        if resoudre_contenu(page, cible) is None:
            erreurs.append(f"{page} : lien interne introuvable : {cible}")


def attributs_capture(appel):
    return dict(re.findall(r'(\w+)="([^"]*)"', appel))


def verifier_guide():
    configuration = charger_configuration_demo(DONNEES_DEMONSTRATION)
    with DONNEES_GUIDE.open(encoding="utf-8") as fichier:
        nomenclature = yaml.safe_load(fichier)
    categories = set(nomenclature["categories"])
    publics = set(nomenclature["publics"])
    statuts = set(nomenclature["statuts"])
    captures_declarees = set(CAPTURES_GENERALES)
    captures_guide_declarees = set()
    for scenario in configuration["scenarios"]:
        for cle in ("capture", "capture_mobile"):
            if cle not in scenario:
                continue
            capture = f"captures/{scenario[cle]}"
            captures_declarees.add(capture)
            if capture.startswith("captures/guide/"):
                captures_guide_declarees.add(capture)

    erreurs = []
    captures_utilisees = set()
    fiches = []
    for page in sorted(GUIDE.rglob("*.md")):
        entete, corps = lire_entete(page)
        verifier_liens(page, corps, erreurs)
        for appel in re.findall(r"{{<\s*capture-guide\s+([^>]+)>}}", corps):
            attributs = attributs_capture(appel)
            manquants = {"src", "alt", "caption"} - set(attributs)
            if manquants:
                erreurs.append(
                    f"{page} : capture-guide sans " + ", ".join(sorted(manquants))
                )
                continue
            source = attributs["src"]
            captures_utilisees.add(source)
            if source not in captures_declarees:
                erreurs.append(
                    f"{page} : capture non déclarée dans la démonstration : {source}"
                )

        if not entete.get("fiche"):
            continue
        fiches.append(page)
        manquants = CHAMPS_FICHE - set(entete)
        if manquants:
            erreurs.append(
                f"{page} : métadonnées manquantes : {', '.join(sorted(manquants))}"
            )
            continue
        if entete["categorie"] not in categories:
            erreurs.append(f"{page} : catégorie inconnue : {entete['categorie']}")
        inconnus = set(entete["publics"]) - publics
        if inconnus:
            erreurs.append(f"{page} : publics inconnus : {', '.join(sorted(inconnus))}")
        if entete["statut"] not in statuts:
            erreurs.append(f"{page} : statut inconnu : {entete['statut']}")
        if not entete["intentions"]:
            erreurs.append(f"{page} : aucune intention de recherche.")

    non_utilisees = captures_guide_declarees - captures_utilisees
    if non_utilisees:
        erreurs.append(
            "Captures du guide déclarées mais non utilisées : "
            + ", ".join(sorted(non_utilisees))
        )

    if erreurs:
        raise RuntimeError("\n".join(erreurs))
    print(
        f"Guide vérifié : {len(fiches)} fiches, "
        f"{len(captures_utilisees)} captures utilisées, liens internes valides."
    )


if __name__ == "__main__":
    verifier_guide()
