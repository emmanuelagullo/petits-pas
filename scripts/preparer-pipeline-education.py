#!/usr/bin/env python3
"""Préparer la publication automatique ou son attente manuelle sans avertissement."""
import argparse
import json
import os
from pathlib import Path

from source_inria import SourceEnAttente, selectionner_source


def configuration(attente=None, identite=None):
    # JSON est également un document YAML valide ; aucune dépendance ajoutée.
    result = {"include": [{"local": "/.gitlab/ci/publication-education-taches.yml"}]}
    if identite is not None:
        result["pwa-publication"] = {"variables": identite}
    if attente:
        # Bloquant : les erreurs de l'import restent fatales après le lancement.
        # Aucun allow_failure:true qui masquerait une publication défectueuse.
        result["source-inria"] = {
            "when": "manual", "allow_failure": False,
            "manual_confirmation": "Relancer après réussite du pipeline Inria du même commit. La publication revérifiera tous les contrôles.",
        }
    return result


def preparer(destination):
    attente = None
    try:
        source = selectionner_source(os.environ.get("CI_COMMIT_TAG"), os.environ.get("CI_COMMIT_SHA"),
                                     os.environ.get("CI_COMMIT_REF_NAME", "main"), distinguer_attente=True)
        print("Validation Inria disponible : pipeline", source["pipeline_id"], "— publication automatique.")
    except SourceEnAttente as error:
        attente = str(error)
        print("Publication non lancée :", attente)
        print("Dans le pipeline enfant, lancer source-inria après la validation Inria. Aucun artefact n'a été publié.")
    # Résoudre ici, dans le job parent, plutôt que dépendre d'une expansion
    # de variables à travers deux déclenchements successifs.
    identite = {
        "PWA_SOURCE_PROJECT": os.environ["CI_PROJECT_PATH"],
        "PWA_SOURCE_PROJECT_ID": os.environ["CI_PROJECT_ID"],
        "PWA_SOURCE_PIPELINE_ID": os.environ["CI_PIPELINE_ID"],
        "PWA_SOURCE_SHA": os.environ["CI_COMMIT_SHA"],
        "PWA_SOURCE_REF": os.environ["CI_COMMIT_REF_NAME"],
        "PWA_SOURCE_TAG": os.environ.get("CI_COMMIT_TAG", ""),
    }
    print("Identité PWA transmise :", json.dumps(identite, ensure_ascii=False))
    destination.write_text(json.dumps(configuration(attente, identite), ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    preparer(parser.parse_args().destination)


if __name__ == "__main__":
    main()
