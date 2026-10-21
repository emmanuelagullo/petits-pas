#!/usr/bin/env python3
"""Préparer la publication automatique ou son attente manuelle sans avertissement."""
import argparse
import json
import os
from pathlib import Path

from source_inria import SourceEnAttente, selectionner_source


def configuration(attente=None):
    # JSON est également un document YAML valide ; aucune dépendance ajoutée.
    result = {"include": [{"local": "/.gitlab/ci/publication-education-taches.yml"}]}
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
    destination.write_text(json.dumps(configuration(attente), ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    preparer(parser.parse_args().destination)


if __name__ == "__main__":
    main()
