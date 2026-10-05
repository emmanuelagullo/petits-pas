#!/usr/bin/env python3
"""Produit des PDF synthétiques reproductibles pour mesurer la phase 4."""

import argparse
from dataclasses import asdict
import importlib.metadata
import importlib.util
import json
import logging
import platform
import sys
import time
from pathlib import Path

from weasyprint import CSS, HTML

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from suivi.services.medias import POLITIQUE_EQUILIBREE, normaliser_image


GENERATEUR_PATH = Path(__file__).with_name("generer-images-recette.py")
SPEC = importlib.util.spec_from_file_location("generer_images_recette", GENERATEUR_PATH)
GENERATEUR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATEUR)


class _CollecteurAvertissements(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


CSS_RECETTE = """
@page { size: A4; margin: 16mm; }
body { color: #24333a; font: 11pt sans-serif; }
.page { break-after: page; min-height: 250mm; }
.page:last-child { break-after: auto; }
.entete { display: flex; align-items: center; gap: 8mm; }
.icone { width: 12mm; height: 12mm; }
.trace { display: block; max-width: 100%; max-height: 12rem; margin-top: 8mm; }
.couverture { display: block; max-width: 100%; max-height: 155mm; margin: 14mm auto; }
.cadre { border: 1px solid #b8c7cd; border-radius: 4mm; padding: 6mm; }
"""


def scenarios(images_dir):
    traces = [images_dir / f"trace-{numero:02d}.jpg" for numero in range(1, 16)]
    return {
        "sans-photo": {"traces": []},
        "une-photo": {"traces": traces[:1]},
        "cinq-photos": {"traces": traces[:5]},
        "quinze-photos": {"traces": traces},
        "couverture-et-cinq-photos": {
            "couverture": images_dir / "couverture-ecole-classe.jpg",
            "traces": traces[:5],
        },
    }


def _normaliser_images(images_dir, destination):
    destination.mkdir(parents=True, exist_ok=True)
    debut = time.perf_counter()
    fichiers = []
    for source in sorted(images_dir.glob("trace-*.jpg")):
        if source.name == "trace-tres-grande.jpg":
            continue
        resultat = normaliser_image(source.read_bytes(), variante="pdf")
        cible = destination / source.name
        cible.write_bytes(resultat.contenu)
        fichiers.append({
            "fichier": source.name,
            "octets_source": source.stat().st_size,
            "octets_normalises": len(resultat.contenu),
            "largeur": resultat.largeur,
            "hauteur": resultat.hauteur,
            "qualite": resultat.qualite,
            "objectif_atteint": resultat.objectif_atteint,
        })
    couverture = images_dir / "couverture-ecole-classe.jpg"
    resultat = normaliser_image(
        couverture.read_bytes(), famille="couverture", variante="pdf"
    )
    cible = destination / couverture.name
    cible.write_bytes(resultat.contenu)
    fichiers.append({
        "fichier": couverture.name,
        "octets_source": couverture.stat().st_size,
        "octets_normalises": len(resultat.contenu),
        "largeur": resultat.largeur,
        "hauteur": resultat.hauteur,
        "qualite": resultat.qualite,
        "objectif_atteint": resultat.objectif_atteint,
    })
    return {
        "secondes": round(time.perf_counter() - debut, 3),
        "fichiers": fichiers,
    }


def _uri(chemin):
    return Path(chemin).resolve().as_uri()


def _html_scenario(configuration, pages):
    couverture = configuration.get("couverture")
    traces = configuration["traces"]
    icone = RACINE / "referentiel/static/referentiel/icones/livre.svg"
    blocs = []
    for numero in range(pages):
        contenu = [
            '<section class="page">',
            '<div class="entete">',
            f'<img class="icone" src="{_uri(icone)}" alt="">',
            f"<h1>Mes acquisitions — page {numero + 1}</h1>",
            "</div>",
            '<div class="cadre"><h2>Une production fictive</h2>',
            "<p>Cette page synthétique exerce la composition du carnet sans donnée réelle.</p>",
        ]
        if numero == 0 and couverture:
            contenu.append(f'<img class="couverture" src="{_uri(couverture)}" alt="">')
        if numero < len(traces):
            contenu.append(f'<img class="trace" src="{_uri(traces[numero])}" alt="">')
        contenu.extend(("</div>", "</section>"))
        blocs.append("".join(contenu))
    return "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>" + "".join(blocs) + "</body></html>"


def recetter(destination, pages=22, configurations=None):
    destination = Path(destination)
    images_dir = destination / "images"
    pdf_dir = destination / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    manifeste = GENERATEUR.generer(images_dir)
    mesure_normalisation = None
    if configurations is None:
        configurations = {
            f"brut-{nom}": configuration
            for nom, configuration in scenarios(images_dir).items()
        }
        images_normalisees = destination / "images-equilibrees-pdf"
        mesure_normalisation = _normaliser_images(images_dir, images_normalisees)
        configurations.update({
            f"equilibre-{nom}": configuration
            for nom, configuration in scenarios(images_normalisees).items()
        })
    resultats = []

    for nom, configuration in configurations.items():
        html = _html_scenario(configuration, pages)
        collecteur = _CollecteurAvertissements()
        journal_weasyprint = logging.getLogger("weasyprint")
        journal_weasyprint.addHandler(collecteur)
        debut = time.perf_counter()
        try:
            document = HTML(string=html, base_url=RACINE.as_uri()).render(
                stylesheets=[CSS(string=CSS_RECETTE)]
            )
            chemin_pdf = pdf_dir / f"{nom}.pdf"
            document.write_pdf(chemin_pdf)
            duree = time.perf_counter() - debut
        finally:
            journal_weasyprint.removeHandler(collecteur)
        fichiers = list(configuration.get("traces", []))
        if configuration.get("couverture"):
            fichiers.append(configuration["couverture"])
        resultats.append(
            {
                "scenario": nom,
                "photos": len(configuration.get("traces", [])),
                "couverture": bool(configuration.get("couverture")),
                "pages": len(document.pages),
                "octets_entree": sum(Path(fichier).stat().st_size for fichier in fichiers),
                "octets_pdf": chemin_pdf.stat().st_size,
                "secondes_generation": round(duree, 3),
                "avertissements_weasyprint": collecteur.messages,
                "pdf": chemin_pdf.relative_to(destination).as_posix(),
            }
        )

    rapport = {
        "format": "petits-pas-recette-pdf",
        "version": 1,
        "avertissement": (
            "Mesure synthétique du moteur PDF, utile pour comparer des évolutions ; "
            "elle ne remplace pas la validation visuelle d'un carnet Petits Pas complet."
        ),
        "environnement": {
            "python": platform.python_version(),
            "pillow": importlib.metadata.version("Pillow"),
            "weasyprint": importlib.metadata.version("weasyprint"),
        },
        "manifeste_images": "images/manifest.json",
        "images_generees": len(manifeste["images"]),
        "profil_equilibre": asdict(POLITIQUE_EQUILIBREE),
        "normalisation": mesure_normalisation,
        "resultats": resultats,
    }
    (destination / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return rapport


def main():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--destination", type=Path, default=Path(".recette-medias"))
    analyseur.add_argument("--pages", type=int, default=22)
    arguments = analyseur.parse_args()
    if arguments.pages < 1:
        analyseur.error("--pages doit être supérieur ou égal à 1")
    rapport = recetter(arguments.destination, arguments.pages)
    for resultat in rapport["resultats"]:
        print(
            f"{resultat['scenario']}: {resultat['pages']} pages, "
            f"{resultat['octets_pdf']} octets, {resultat['secondes_generation']:.3f} s"
        )
    print(f"Rapport : {arguments.destination / 'rapport.json'}")


if __name__ == "__main__":
    main()
