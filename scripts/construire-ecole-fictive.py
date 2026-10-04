#!/usr/bin/env python3
"""Générer uniquement des données fictives dans une base temporaire indépendante."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def commit_sources():
    for nom in ("CI_COMMIT_SHA", "GITHUB_SHA"):
        valeur = os.environ.get(nom, "")
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", valeur):
            return valeur.lower()
    from carnet.version import git
    valeur = git("rev-parse", "HEAD")
    return valeur if re.fullmatch(r"[0-9a-fA-F]{40,64}", valeur) else None


def construire(destination):
    sys.path.insert(0, str(ROOT))
    from suivi.paquet_local import creer_sauvegarde
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    empreinte = hashlib.sha256()
    for dossier in ["carnet", "comptes", "suivi", "referentiel", "site/data"]:
        for fichier in sorted((ROOT / dossier).rglob("*")):
            if fichier.is_file() and fichier.suffix in {".py", ".yaml", ".svg"}:
                empreinte.update(fichier.relative_to(ROOT).as_posix().encode())
                empreinte.update(fichier.read_bytes())
    empreinte.update(Path(__file__).read_bytes())
    revision = empreinte.hexdigest()
    commit = commit_sources()
    notice = destination.with_suffix(".json")
    if destination.exists() and not notice.exists():
        raise ValueError("Un fichier existe sans notice fictive : remplacement refusé.")
    if destination.exists() and notice.exists():
        ancien = json.loads(notice.read_text())
        if ancien.get("donnees") != "fictives uniquement":
            raise ValueError("Ce fichier n'est pas identifié comme un ZIP fictif généré.")
        if ancien.get("source_commit") == commit and ancien.get("scenario_sha256") == revision and ancien.get("zip_sha256") == hashlib.sha256(destination.read_bytes()).hexdigest():
            return
    with tempfile.TemporaryDirectory(prefix="petits-pas-fictif-") as temporaire:
        paquet = Path(temporaire) / "paquet"
        paquet.mkdir(); (paquet / "media").mkdir()
        cle = "cle-publique-ecole-fictive-sans-donnees-reelles"
        (paquet / "secret-key").write_text(cle)
        # Éliminer les paramètres privés, bases distantes, 2FA et fournisseurs hérités.
        environnement = {k: v for k, v in os.environ.items()
                         if not k.startswith(("CARNET_", "DATABASE_", "DJANGO_"))}
        environnement.update({"DATABASE_URL": "", "CARNET_SQLITE_PATH": str(paquet / "carnet.sqlite3"),
            "CARNET_MEDIA_ROOT": str(paquet / "media"), "CARNET_SECRET_KEY": cle,
            "CARNET_ENVIRONNEMENT_EPHEMERE": "oui", "CARNET_EMAIL_DESACTIVE": "oui",
            "CARNET_ANTIBRUTEFORCE": "non", "CARNET_DEBUG": "1", "CARNET_HOSTS": "localhost,127.0.0.1"})
        for commande in [("migrate", "--noinput"), ("preparer_demonstration",)]:
            subprocess.run([sys.executable, str(ROOT / "manage.py"), *commande],
                cwd=ROOT, env=environnement, check=True, stdout=subprocess.DEVNULL)
        provisoire = Path(temporaire) / "ecole.zip"
        creer_sauvegarde(paquet, provisoire)
        destination.write_bytes(provisoire.read_bytes())
    import yaml
    configuration = yaml.safe_load((ROOT / "site/data/demonstration.yaml").read_text())
    notice.write_text(json.dumps({"identifiants": configuration["identifiants"],"donnees": "fictives uniquement", "source_commit": commit,
        "scenario_sha256": revision, "zip_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "format_zip": 1, "installation": "À ouvrir dans l'espace d'essai ; une restauration remplace l'école locale."},
        ensure_ascii=False, indent=2) + "\n")
    print("ZIP fictif préparé :", destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "referentiel/demo/ecole-fictive.zip")
    construire(parser.parse_args().destination)
