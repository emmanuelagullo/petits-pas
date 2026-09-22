#!/usr/bin/env python3
"""Génère les captures publiques depuis une démonstration locale fictive."""

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from suivi.configuration_demo import charger_configuration_demo


def attendre_application(base_url, tentatives=60):
    for _ in range(tentatives):
        try:
            with urllib.request.urlopen(f"{base_url}/health/", timeout=1) as reponse:
                if reponse.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    raise RuntimeError("La démonstration locale ne répond pas.")


def capturer(page: Page, chemin: Path):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    page.add_style_tag(
        content="""
            *, *::before, *::after {
                animation: none !important;
                caret-color: transparent !important;
                transition: none !important;
            }
        """
    )
    page.screenshot(path=chemin)
    print(f"Capture créée : {chemin}")


def profil(demonstration, identifiant):
    return next(
        profil
        for profil in demonstration["profils"]
        if profil["id"] == identifiant
    )


def connecter(page, base_url, demonstration, identifiant):
    personnage = profil(demonstration, identifiant)
    type_compte = personnage.get("compte_initial", "enseignant")
    mot_de_passe = demonstration["identifiants"][type_compte]["mot_de_passe"]
    page.context.clear_cookies()
    page.goto(f"{base_url}/connexion/")
    page.locator("#nom_utilisateur").fill(personnage["utilisateur"])
    page.locator("#mdp").fill(mot_de_passe)
    page.get_by_role("button", name="Entrer").click()
    page.get_by_role("heading", name="Les classes").wait_for()


def ouvrir_classe(page, demonstration, identifiant):
    nom = demonstration["classes"][identifiant]["nom"]
    page.get_by_role("link", name=re.compile(f"^{re.escape(nom)}")).first.click()
    page.get_by_role("heading", name=nom, exact=True).wait_for()


def jouer_scenario(page, base_url, output, demonstration, scenario):
    connecter(page, base_url, demonstration, scenario["profil"])
    parcours = scenario["parcours"]
    if parcours == "equipe_direction":
        page.get_by_role("link", name="Gérer l'école").click()
        page.get_by_role("link", name="Équipe pédagogique").click()
        page.get_by_role("heading", name="Équipe pédagogique").wait_for()
    else:
        ouvrir_classe(page, demonstration, scenario["classe"])
        if parcours == "contribution":
            page.locator(".liste .entree").first.click()
            page.get_by_role(
                "heading", name=re.compile(r"^Ajouter une contribution pour")
            ).wait_for()
    capturer(page, output / scenario["capture"])


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--base-url", required=True)
    analyseur.add_argument("--output", type=Path, required=True)
    options = analyseur.parse_args()

    demonstration = charger_configuration_demo(
        RACINE / "site" / "data" / "demonstration.yaml"
    )

    options.output.mkdir(parents=True, exist_ok=True)
    attendre_application(options.base_url)

    with sync_playwright() as playwright:
        lancement = {"args": ["--disable-dev-shm-usage"]}
        executable_chromium = os.environ.get(
            "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"
        )
        if executable_chromium:
            lancement["executable_path"] = executable_chromium
        navigateur = playwright.chromium.launch(**lancement)
        contexte = navigateur.new_context(
            viewport={"width": 1440, "height": 1000},
            color_scheme="light",
            locale="fr-FR",
            reduced_motion="reduce",
            timezone_id="Europe/Paris",
        )
        page = contexte.new_page()

        page.goto(f"{options.base_url}/connexion/")
        page.get_by_role("heading", name="Carnet de suivi des apprentissages").wait_for()
        capturer(page, options.output / "connexion.png")

        connecter(page, options.base_url, demonstration, "remi")
        premiere_classe = page.locator(".liste .entree").first
        nom_classe = premiere_classe.locator(".principal").inner_text().strip()
        premiere_classe.click()
        page.get_by_role("heading", name=nom_classe).wait_for()
        capturer(page, options.output / "classe.png")

        premier_eleve = page.locator(".liste .entree").first
        nom_eleve = premier_eleve.locator(".principal").inner_text().strip()
        premier_eleve.click()
        page.get_by_role("heading", name=nom_eleve, exact=True).wait_for()
        capturer(page, options.output / "acquisitions.png")

        page.get_by_role("link", name=re.compile(r"Voir le carnet de")).click()
        page.locator("article.carnet").wait_for()
        page.locator(".date-edition").evaluate(
            "element => element.textContent = 'Édité le 1 septembre 2026'"
        )
        page.locator(".pied").evaluate(
            "element => element.textContent = "
            "'Carnet édité le 1 septembre 2026 par Ma Belle École.'"
        )
        capturer(page, options.output / "carnet.png")

        connecter(page, options.base_url, demonstration, "diane")
        page.get_by_role("link", name="Gérer l'école").click()
        page.get_by_role("heading", name="Gérer l'école").wait_for()
        capturer(page, options.output / "direction.png")

        for scenario in demonstration["scenarios"]:
            jouer_scenario(
                page,
                options.base_url,
                options.output,
                demonstration,
                scenario,
            )

        navigateur.close()


if __name__ == "__main__":
    main()
