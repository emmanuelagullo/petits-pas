#!/usr/bin/env python3
"""Construire un site statique PWA expérimental ; jamais de base d'école."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import subprocess
import urllib.request
import urllib.error
import http.client
import ssl
import tempfile
import time
from urllib.parse import urldefrag, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from publication import identity, release_notes

ROOT = Path(__file__).resolve().parent.parent
from pas_communs.construction_pwa import RUNTIME_314_0_7
RUNTIME = RUNTIME_314_0_7
PYODIDE = RUNTIME.version
BASE = RUNTIME.base


from pas_communs.construction_pwa import telecharger, verifier_runtime, nettoyer_runtime
from pas_communs.navigateur import copier_ressources


def preparer_wheels(wheels, cache=None):
    """Même wheel épinglé que serveur/bureau ; cache local sans accès à la release."""
    lignes = [ligne.strip() for ligne in (ROOT / "requirements-communs.txt").read_text().splitlines()
              if ligne.strip() and not ligne.lstrip().startswith("#")]
    if len(lignes) != 1 or not lignes[0].startswith("pas-communs @ "):
        raise ValueError("Dépendance du socle invalide.")
    url, fragment = urldefrag(lignes[0].split(" @ ", 1)[1])
    if not fragment.startswith("sha256=") or len(fragment[7:]) != 64:
        raise ValueError("Empreinte du socle absente.")
    empreinte = fragment[7:]
    nom = Path(urlsplit(url).path).name
    if not nom.startswith("pas_communs-") or not nom.endswith("-py3-none-any.whl"):
        raise ValueError("Le socle doit être un wheel Python pur.")
    cible = wheels / nom
    if cache:
        source = cache.resolve() / nom
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != empreinte:
            raise ValueError("Wheel du socle absent ou altéré dans le cache.")
        if source.resolve() != cible.resolve():
            shutil.copyfile(source, cible)
    else:
        telecharger(url, cible, empreinte)
    for ancien in wheels.glob("pas_communs-*.whl"):
        if ancien != cible:
            ancien.unlink()
    # pip suit toujours une URL directe, même avec --no-index. Retirer seulement
    # l'inclusion déjà traitée ci-dessus pour conserver un vrai mode hors réseau.
    exigences = (ROOT / "pwa/requirements.txt").read_text().splitlines()
    exigences = [ligne for ligne in exigences if ligne.strip() != "-r ../requirements-communs.txt"]
    with tempfile.TemporaryDirectory() as dossier:
        requirement = Path(dossier) / "pwa.txt"
        requirement.write_text("\n".join(exigences) + "\n")
        subprocess.run([
            sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps",
            "--dest", str(wheels), "-r", str(requirement),
            *(["--no-index", "--find-links", str(cache.resolve())] if cache else []),
        ], check=True)


def verifier_python_construction():
    """Python hôte : distinct de celui du Worker Pyodide et de sa bibliothèque."""
    if sys.version_info < (3, 12):
        raise SystemExit("Construction PWA : Python 3.12 ou plus récent requis.")
    print(f"Python constructeur : {sys.version.split()[0]} ({sys.executable}) ; "
          f"Python embarqué : {RUNTIME.python} (Pyodide {RUNTIME.version}, ABI {RUNTIME.abi})",
          flush=True)


def main():
    verifier_python_construction()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ROOT / "dist/pwa")
    parser.add_argument("--runtime", type=Path, help="Cache Pyodide déjà téléchargé")
    parser.add_argument("--wheels", type=Path, help="Cache des wheels Python")
    parser.add_argument("--test", action="store_true", help="Activer le protocole d'injection pour les tests fictifs")
    args = parser.parse_args()
    output = args.sortie.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        parser.error("La sortie ne doit pas contenir le dépôt")
    output.mkdir(parents=True, exist_ok=True)
    (output / "resultats-tests.json").unlink(missing_ok=True)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    # Éventuels fragments laissés par un arrêt brutal du constructeur.
    for fragment in runtime.glob("*.part"):
        fragment.unlink()

    cache_runtime = args.runtime.resolve() if args.runtime else runtime
    cache_runtime.mkdir(parents=True, exist_ok=True)

    def download(name, empreinte=None):
        source = cache_runtime / name
        telecharger(BASE + name, source, empreinte)
        target = runtime / name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        return name

    download("pyodide-lock.json")
    lock = json.loads((runtime / "pyodide-lock.json").read_text())
    verifier_runtime(lock, runtime=RUNTIME)
    selected = set()
    def select(name):
        if name in selected:
            return
        selected.add(name)
        for dependency in lock["packages"][name]["depends"]:
            select(dependency)
    for name in ["pillow", "pyyaml", "micropip", "pycryptodome"]:
        select(name)
    packages = [lock["packages"][name] for name in sorted(selected)]
    names = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip"]
    names += [package["file_name"] for package in packages]
    empreintes = {p["file_name"]: p["sha256"] for p in packages}
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda name: download(name, empreintes.get(name)), names))
    for package in packages:
        if hashlib.sha256((runtime / package["file_name"]).read_bytes()).hexdigest() != package["sha256"]:
            raise RuntimeError("Wheel WASM altérée : " + package["file_name"])
    nettoyer_runtime(runtime, set(names) | {"pyodide-lock.json"})
    wheels = output / "wheels"
    wheels.mkdir(exist_ok=True)
    preparer_wheels(wheels, args.wheels)
    subprocess.run([sys.executable, str(ROOT / "scripts/construire-ecole-fictive.py")], check=True)
    shutil.copyfile(ROOT / "referentiel/demo/ecole-fictive.zip", output / "ecole-fictive.zip")
    shutil.copyfile(ROOT / "referentiel/demo/ecole-fictive.json", output / "ecole-fictive.json")
    with ZipFile(output / "application.zip", "w", ZIP_DEFLATED) as archive:
        for folder in ["carnet", "comptes", "suivi", "referentiel", "pwa"]:
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                if (folder == "pwa" and "templates" not in path.relative_to(ROOT / folder).parts
                        and path.name not in {"bridge.py", "settings.py", "urls.py", "views.py", "media_storage.py", "transfers.py", "limits.py", "crypto.py"}):
                    continue
                if path.name.startswith("tests") or path.suffix not in {".py", ".html", ".yaml", ".css", ".js", ".svg", ".png", ".jpg", ".json"}:
                    continue
                entry = ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
    for name in ["index.html", "essai.html", "apercu.html", "shell.js", "worker.js", "storage.js", "lazy_media.js", "transfers.js", "transport.js", "capabilities.js", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png"]:
        shutil.copyfile(ROOT / "pwa" / name, output / name)
    for folder in [ROOT / "referentiel/static", ROOT / "suivi/static"]:
        shutil.copytree(folder, output / "static", dirs_exist_ok=True)
    copier_ressources(output / "socle")
    source = identity()
    notes = release_notes(source['tag'])
    (output / "notes-version.md").write_bytes(notes.encode("utf-8"))
    (output / "nouveautes.html").write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nouveautés de Petits Pas</title><style>body{font:1rem system-ui;max-width:52rem;margin:2rem auto;padding:0 1rem;color:#234}pre{white-space:pre-wrap;font:inherit;line-height:1.6}</style><h1>Nouveautés de Petits Pas</h1><p>Version ' + html.escape(source['application_version']) + '</p><pre>' + html.escape(notes) + '</pre></html>', encoding='utf-8')
    build = hashlib.sha256()
    build.update(json.dumps(source, sort_keys=True).encode())
    # Une version de test ne doit jamais partager le cache de la distribution.
    build.update(b"test=1" if args.test else b"test=0")
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {"sw.js", "config.json"}:
            build.update(path.relative_to(output).as_posix().encode())
            build.update(path.read_bytes())
    version = "pwa." + build.hexdigest()[:16]
    (output / "sw.js").write_text((ROOT / "pwa/sw.js").read_text().replace("__BUILD__", version))
    assets = [{"url": "/" + path.relative_to(output).as_posix(),
               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
              for path in sorted(output.rglob("*")) if path.is_file() and path.name != "config.json"]
    config = {**source, "version": version, "pyodide": PYODIDE, "testMode": args.test,
              "python": lock["info"]["python"],
              "runtime_packages": {name: lock["packages"][name]["version"] for name in sorted(selected)},
              "wheels": sorted(path.name for path in wheels.glob("*.whl")), "assets": assets}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"Application navigateur construite : {output} ({version}, {sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) / 1024**2:.1f} Mio non compressés)")


if __name__ == "__main__":
    main()
