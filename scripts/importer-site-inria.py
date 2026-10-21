#!/usr/bin/env python3
"""Importer les captures et l'école fictive du pipeline Inria qualifié."""
import json
import os
from pathlib import Path
import tempfile

from source_inria import extraire_site, selectionner_source, telecharger, trouver_job


def main():
    source = selectionner_source(os.environ.get("CI_COMMIT_TAG"), os.environ.get("CI_COMMIT_SHA"))
    job, url = trouver_job(source, "captures-demonstration")
    with tempfile.TemporaryDirectory(prefix="site-inria-") as temporary:
        archive = Path(temporary) / "captures.zip"
        telecharger(url, archive)
        extraire_site(archive, Path.cwd())
    source["captures_job_id"] = job["id"]
    Path("source-inria.json").write_text(json.dumps(source, indent=2) + "\n")
    print("Captures et école fictive importées du pipeline Inria", source["pipeline_id"])


if __name__ == "__main__":
    main()
