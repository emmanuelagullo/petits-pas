"""Version du code, commune aux déploiements serveur et autonomes."""

import os
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TAG = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-[A-Za-z0-9.-]+)?\Z")


def git(*arguments):
    try:
        return subprocess.run(
            ["git", *arguments], cwd=RACINE, check=True, capture_output=True,
            text=True, timeout=8,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def version_pour_commit(commit, tags):
    """Un tag exact nomme une release ; un ancêtre tagué ne la nomme pas."""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        return "dev"
    correspondances = sorted(nom for nom, sha in tags.items() if sha == commit and TAG.fullmatch(nom))
    if len(correspondances) > 1:
        raise ValueError(f"Plusieurs versions désignent le commit {commit}: {correspondances}")
    return correspondances[0] if correspondances else f"dev.{commit[:8]}"


def tags_distants():
    # Render ne garantit pas que son répertoire de travail inclut les tags.
    # La forge publique est identique pour les deux miroirs du projet.
    depot = os.environ.get("PETITS_PAS_DEPOT_VERSIONS", "https://github.com/emmanuelagullo/petits-pas.git")
    sortie = git("ls-remote", "--tags", depot)
    tags = {}
    for ligne in sortie.splitlines():
        sha, _, reference = ligne.partition("\trefs/tags/")
        nom = reference.removesuffix("^{}")
        if TAG.fullmatch(nom) and (reference.endswith("^{}") or nom not in tags):
            tags[nom] = sha
    return tags


def version_application():
    if getattr(sys, "frozen", False):
        fichier = Path(sys._MEIPASS) / "version-application.txt"
        return fichier.read_text(encoding="utf-8").strip()
    commit = os.environ.get("CI_COMMIT_SHA") or os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD")
    tag_ci = os.environ.get("CI_COMMIT_TAG") or (os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None)
    if tag_ci:
        if not TAG.fullmatch(tag_ci):
            raise ValueError(f"Tag de version invalide : {tag_ci}")
        return tag_ci
    if os.environ.get("CI_COMMIT_SHA") or os.environ.get("GITHUB_REF_TYPE") == "branch":
        return version_pour_commit(commit, {})
    if os.environ.get("RENDER_GIT_COMMIT"):
        return version_pour_commit(commit, tags_distants())
    # En développement local et dans la CI, les tags locaux suffisent.
    tags = {}
    for nom in git("tag", "--points-at", "HEAD").splitlines():
        tags[nom] = commit
    return version_pour_commit(commit, tags)


if __name__ == "__main__":
    print(version_application())
