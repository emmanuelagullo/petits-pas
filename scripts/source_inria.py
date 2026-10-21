"""Retrouver les artefacts qualifiés d’une référence et d’un commit exacts."""
import json
import re
import stat
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from zipfile import ZipFile

API = "https://gitlab.inria.fr/api/v4"
PROJECT = "petits-pas/petits-pas"
MAX_BYTES = 256 * 1024**2


def json_request(url):
    request = urllib.request.Request(url, headers={"User-Agent": "PetitsPas-publication-education"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(8 * 1024**2 + 1)
    if len(raw) > 8 * 1024**2:
        raise ValueError("Réponse API trop volumineuse.")
    return json.loads(raw)


def selectionner_source(tag, commit, ref="main"):
    if tag:
        if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-[A-Za-z0-9.-]+)?", tag):
            raise ValueError("Un tag numérique est requis pour le miroir Éducation.")
        ref = tag
    elif not ref or len(ref) > 255 or any(ord(c) < 32 for c in ref):
        raise ValueError("Branche source invalide.")
    if not re.fullmatch(r"[a-f0-9]{40}", commit or ""):
        raise ValueError("Commit source invalide.")
    project = json_request(API + "/projects/" + urllib.parse.quote(PROJECT, safe=""))
    if project["path_with_namespace"] != PROJECT or not str(project["id"]).isdecimal():
        raise ValueError("Projet Inria inattendu.")
    base = API + "/projects/" + str(project["id"])
    if tag:
        encoded_tag = urllib.parse.quote(tag, safe="")
        inria_tag = json_request(base + "/repository/tags/" + encoded_tag)
        github_tag = json_request("https://api.github.com/repos/emmanuelagullo/petits-pas/commits/" + encoded_tag)
        if inria_tag["commit"]["id"] != commit or github_tag["sha"] != commit:
            raise ValueError("Le tag ne désigne pas le même commit sur les trois hébergements.")
    else:
        # Les branches peuvent avancer pendant la publication : vérifier le SHA,
        # puis sélectionner son pipeline exact, sans suivre leur dernière tête.
        github_commit = json_request("https://api.github.com/repos/emmanuelagullo/petits-pas/commits/" + commit)
        if github_commit["sha"] != commit:
            raise ValueError("Commit absent ou différent sur GitHub.")
    query = urllib.parse.urlencode({"ref": ref, "sha": commit, "status": "success",
                                   "order_by": "id", "sort": "desc", "per_page": 1})
    candidates = json_request(base + "/pipelines?" + query)
    if not candidates:
        raise ValueError("Aucun pipeline Inria réussi pour cette référence et ce commit. Attendre sa réussite puis relancer.")
    pipeline = json_request(base + "/pipelines/" + str(candidates[0]["id"]))
    if (pipeline["sha"] != commit or pipeline["ref"] != ref
            or pipeline["status"] != "success" or pipeline.get("source") not in ("push", "web", "api")):
        raise ValueError("Pipeline Inria inattendu ou non réussi.")
    return {"api": API, "project": PROJECT, "project_id": str(project["id"]),
            "pipeline_id": str(pipeline["id"]), "commit": commit, "tag": tag or None, "ref": ref}


def trouver_job(source, name):
    base = source["api"] + "/projects/" + source["project_id"]
    matches = []
    page = 1
    while True:
        jobs = json_request(base + "/pipelines/" + source["pipeline_id"]
                            + "/jobs?include_retried=false&per_page=100&page=" + str(page))
        matches.extend(job for job in jobs if job["name"] == name)
        if len(jobs) < 100:
            break
        page += 1
    if len(matches) != 1:
        raise ValueError("Job Inria absent ou ambigu : " + name)
    job = matches[0]
    if (job["status"] != "success" or job["commit"]["id"] != source["commit"]
            or str(job["pipeline"]["id"]) != source["pipeline_id"]):
        raise ValueError("Job Inria non qualifié pour ce commit : " + name)
    return job, base + "/jobs/" + str(job["id"]) + "/artifacts"


def telecharger(url, destination):
    total = 0
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
        while block := response.read(1024**2):
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError("Artefact trop volumineux.")
            output.write(block)


def extraire_site(archive, destination):
    prefixes = ("site/static/captures/", "site/static/essais/")
    with ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if len(entries) > 5000 or sum(info.file_size for info in entries) > MAX_BYTES:
            raise ValueError("Archive de site trop volumineuse.")
        seen = set()
        selected = []
        for info in entries:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or "\\" in name or ".." in parts
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("Chemin ou lien invalide dans l'archive du site.")
            if info.is_dir():
                continue
            normalized = str(PurePosixPath(name))
            if normalized in seen:
                raise ValueError("Chemin répété dans l'archive du site.")
            seen.add(normalized)
            if name.startswith(prefixes):
                selected.append(info)
        if not any(i.filename.startswith(prefixes[0]) for i in selected) or not any(
                i.filename == "site/static/essais/ecole-fictive.zip" for i in selected):
            raise ValueError("Captures ou école fictive absentes de l'artefact.")
        for info in selected:
            target = destination.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(zipped.read(info))
