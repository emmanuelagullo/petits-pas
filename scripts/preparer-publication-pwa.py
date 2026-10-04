#!/usr/bin/env python3
"""Publier l'artefact exact du prototype réussi, sans reconstruction ni secret."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

SOURCE = "petits-pas/petits-pas"
MAX_BYTES = 256 * 1024**2
MAX_FILES = 5000


def require_pages_url(value):
    url = urllib.parse.urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or not re.fullmatch(r"/(?:[a-zA-Z0-9_-]+/)*", url.path or "/") or url.query or url.fragment):
        raise ValueError("La PWA exige une URL HTTPS avec un chemin terminé par /, sans paramètres.")


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_bundle(root):
    config = json.loads((root / "config.json").read_text())
    if config.get("testMode") is not False:
        raise ValueError("Bundle de test ou mode indéterminé : publication refusée.")
    if not re.fullmatch(r"pwa-prototype\.[a-f0-9]{16}", config.get("version", "")):
        raise ValueError("Version du bundle invalide.")
    expected = {"config.json"}
    for asset in config["assets"]:
        url = asset["url"]
        parts = PurePosixPath(url.removeprefix("/")).parts
        if (not url.startswith("/") or not parts or any(p in {".", ".."} for p in parts)
                or "\\" in url or url != "/" + "/".join(parts)):
            raise ValueError("Chemin d'asset invalide.")
        name = "/".join(parts)
        if name in expected or not re.fullmatch(r"[a-f0-9]{64}", asset["sha256"]):
            raise ValueError("Asset répété ou empreinte invalide.")
        expected.add(name)
        if sha256(root.joinpath(*parts)) != asset["sha256"]:
            raise ValueError(f"Asset altéré : {name}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != expected or not {"index.html", "worker.js", "storage.js", "sw.js", "application.zip"} <= actual:
        raise ValueError("Bundle incomplet ou fichiers non déclarés.")
    if any(PurePosixPath(name).name == "secret-key" or name.endswith(".sqlite3") for name in actual):
        raise ValueError("Données locales présentes dans le bundle.")
    return config


def extract_bundle(archive, parent):
    """N'extraire que les statiques vérifiés et le rapport de leur job CI."""
    with ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if (len(entries) > MAX_FILES or sum(e.file_size for e in entries) > MAX_BYTES
                or len({e.filename for e in entries}) != len(entries)):
            raise ValueError("Artefact trop volumineux ou entrées répétées.")
        for entry in entries:
            if not entry.filename.startswith("dist/pwa/") and entry.filename != "resultats-pwa.json":
                continue
            parts = PurePosixPath(entry.filename).parts
            if (entry.filename.startswith("/") or "\\" in entry.filename or ".." in parts
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Chemin ou lien invalide dans l'artefact.")
            if entry.is_dir():
                continue
            target = parent.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(entry) as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination)
    report = parent / "resultats-pwa.json"
    checks = json.loads(report.read_text())
    if not isinstance(checks, list) or not checks or any(not check.get("test") for check in checks):
        raise ValueError("Rapport de tests absent ou invalide.")
    root = parent / "dist/pwa"
    return root, validate_bundle(root), sha256(report)


def json_request(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response), response.headers


def select_job(api, project, pipeline_id, commit):
    """Ne jamais prendre le dernier artefact de main à la place de ce pipeline."""
    info, _ = json_request(api + "/projects/" + urllib.parse.quote(SOURCE, safe=""))
    if str(info["id"]) != project or info["path_with_namespace"] != SOURCE:
        raise ValueError("Projet source inattendu.")
    base = api + "/projects/" + project
    pipeline, _ = json_request(base + "/pipelines/" + pipeline_id)
    if pipeline["sha"] != commit or pipeline["ref"] != info["default_branch"]:
        raise ValueError("Commit ou branche du pipeline inattendu.")
    page, matches = "1", []
    while page:
        jobs, headers = json_request(base + "/pipelines/" + pipeline_id
            + "/jobs?include_retried=false&per_page=100&page=" + page)
        matches.extend(job for job in jobs if job["name"] == "pwa-prototype")
        page = headers.get("X-Next-Page", "")
    if len(matches) != 1:
        raise ValueError("Job pwa-prototype introuvable ou ambigu dans ce pipeline.")
    job = matches[0]
    if (job["status"] != "success" or job["commit"]["id"] != commit
            or str(job["pipeline"]["id"]) != pipeline_id):
        raise ValueError("pwa-prototype n'a pas réussi pour ce commit : publication refusée.")
    return job, base + "/jobs/" + str(job["id"]) + "/artifacts"


def download(url, path):
    total = 0
    with urllib.request.urlopen(url, timeout=60) as source, path.open("wb") as destination:
        while block := source.read(1024**2):
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError("Artefact téléchargé trop volumineux.")
            destination.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--pages-url", required=True)
    args = parser.parse_args()
    require_pages_url(args.pages_url.rstrip("/") + "/")
    if args.destination.exists():
        raise ValueError("Destination déjà présente : publication refusée.")
    project = os.environ["PWA_SOURCE_PROJECT_ID"]
    pipeline = os.environ["PWA_SOURCE_PIPELINE_ID"]
    commit = os.environ["PWA_SOURCE_SHA"]
    if (os.environ["PWA_SOURCE_PROJECT"] != SOURCE or not project.isdecimal()
            or not pipeline.isdecimal() or not re.fullmatch(r"[a-f0-9]{40}", commit)):
        raise ValueError("Référence source invalide.")
    job, url = select_job(os.environ["CI_API_V4_URL"], project, pipeline, commit)
    with tempfile.TemporaryDirectory(prefix="publication-pwa-") as temp:
        parent = Path(temp)
        archive = parent / "artefact.zip"
        download(url, archive)
        root, config, report_hash = extract_bundle(archive, parent)
        shutil.copytree(root, args.destination)
    record = {"source_project": SOURCE, "pipeline_id": pipeline, "job_id": job["id"],
        "commit": commit, "version": config["version"], "tests_sha256": report_hash,
        "url": args.pages_url, "prepared_at": datetime.now(timezone.utc).isoformat()}
    Path("publication-pwa.json").write_text(json.dumps(record, indent=2) + "\n")
    print("Bundle vérifié et prêt pour Pages :", config["version"], args.pages_url)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, BadZipFile, urllib.error.URLError) as error:
        raise SystemExit(f"Publication refusée : {error}") from error
