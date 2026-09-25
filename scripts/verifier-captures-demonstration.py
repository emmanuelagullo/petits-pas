#!/usr/bin/env python3
"""Vérifie l'inventaire et le budget des captures documentaires."""

import argparse
import sys
from pathlib import Path

from PIL import Image

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from suivi.configuration_demo import charger_configuration_demo

CAPTURES_GENERALES = {
    "connexion.png",
    "classe.png",
    "acquisitions.png",
    "carnet.png",
    "direction.png",
    "guide/local/gestion.png",
    "guide/local/sauvegardes.png",
}
TAILLE_MAXIMALE = 2 * 1024 * 1024
BUDGET_TOTAL = 12 * 1024 * 1024


def captures_attendues(configuration):
    attendues = {chemin: "bureau" for chemin in CAPTURES_GENERALES}
    for scenario in configuration["scenarios"]:
        type_capture = "cible" if "cible" in scenario else "bureau"
        attendues[scenario["capture"]] = type_capture
        if "capture_mobile" in scenario:
            attendues[scenario["capture_mobile"]] = "mobile"
    return attendues


def verifier_dimensions(chemin, dimensions, type_capture):
    largeur, hauteur = dimensions
    if type_capture == "bureau" and dimensions != (1440, 1000):
        raise RuntimeError(
            f"{chemin} : dimensions {largeur} × {hauteur}, attendu 1440 × 1000."
        )
    if type_capture == "mobile" and dimensions != (390, 844):
        raise RuntimeError(
            f"{chemin} : dimensions {largeur} × {hauteur}, attendu 390 × 844."
        )
    # Une ligne représentant un membre sans affectation est volontairement
    # très compacte (28 px avec la feuille de style actuelle). On conserve
    # une borne basse pour détecter un sélecteur ou un rendu dégénéré, sans
    # imposer artificiellement du contenu à ce cas documentaire légitime.
    if type_capture == "cible" and not (
        240 <= largeur <= 1440 and 24 <= hauteur <= 3000
    ):
        raise RuntimeError(
            f"{chemin} : cadrage ciblé incohérent ({largeur} × {hauteur})."
        )


def verifier_captures(repertoire, configuration):
    attendues = captures_attendues(configuration)
    presentes = {
        chemin.relative_to(repertoire).as_posix()
        for chemin in repertoire.rglob("*.png")
    }
    manquantes = set(attendues) - presentes
    inattendues = presentes - set(attendues)
    if manquantes:
        raise RuntimeError("Captures manquantes : " + ", ".join(sorted(manquantes)))
    if inattendues:
        raise RuntimeError(
            "Captures non déclarées : " + ", ".join(sorted(inattendues))
        )

    taille_totale = 0
    for chemin_relatif, type_capture in sorted(attendues.items()):
        chemin = repertoire / chemin_relatif
        taille = chemin.stat().st_size
        if taille > TAILLE_MAXIMALE:
            raise RuntimeError(
                f"{chemin_relatif} dépasse 2 Mio ({taille / 1024 / 1024:.2f} Mio)."
            )
        taille_totale += taille
        with Image.open(chemin) as image:
            dimensions = image.size
            if image.format != "PNG":
                raise RuntimeError(f"{chemin_relatif} n'est pas un fichier PNG.")
            image.verify()
        verifier_dimensions(chemin_relatif, dimensions, type_capture)

    if taille_totale > BUDGET_TOTAL:
        raise RuntimeError(
            f"Les captures dépassent le budget de 12 Mio "
            f"({taille_totale / 1024 / 1024:.2f} Mio)."
        )
    print(
        f"{len(attendues)} captures vérifiées, "
        f"{taille_totale / 1024 / 1024:.2f} Mio au total."
    )


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--input", type=Path, required=True)
    options = analyseur.parse_args()
    configuration = charger_configuration_demo(
        RACINE / "site" / "data" / "demonstration.yaml"
    )
    verifier_captures(options.input, configuration)


if __name__ == "__main__":
    main()
