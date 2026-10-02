#!/usr/bin/env python3
"""Construire un site statique PWA expérimental ; jamais de base d'école."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
PYODIDE = "0.28.3"
BASE = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE}/full/"


def main():
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

    def download(name):
        target = runtime / name
        if args.runtime and (args.runtime / name).is_file():
            shutil.copyfile(args.runtime / name, target)
        else:
            with urllib.request.urlopen(BASE + name, timeout=120) as response:
                target.write_bytes(response.read())
        return name

    download("pyodide-lock.json")
    lock = json.loads((runtime / "pyodide-lock.json").read_text())
    selected = set()
    def select(name):
        if name in selected:
            return
        selected.add(name)
        for dependency in lock["packages"][name]["depends"]:
            select(dependency)
    for name in ["sqlite3", "pillow", "pyyaml", "micropip", "hashlib"]:
        select(name)
    packages = [lock["packages"][name] for name in sorted(selected)]
    names = ["pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip"]
    names += [package["file_name"] for package in packages]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, names))
    for package in packages:
        if hashlib.sha256((runtime / package["file_name"]).read_bytes()).hexdigest() != package["sha256"]:
            raise RuntimeError("Wheel WASM altérée : " + package["file_name"])
    wheels = output / "wheels"
    wheels.mkdir(exist_ok=True)
    subprocess.run([
        "python3", "-m", "pip", "download", "--only-binary=:all:", "--no-deps",
        "--dest", str(wheels), "-r", str(ROOT / "pwa/requirements.txt"),
        *(["--no-index", "--find-links", str(args.wheels.resolve())] if args.wheels else []),
    ], check=True)
    with ZipFile(output / "application.zip", "w", ZIP_DEFLATED) as archive:
        for folder in ["carnet", "comptes", "suivi", "referentiel", "pwa"]:
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                if folder == "pwa" and path.name not in {"bridge.py", "settings.py"}:
                    continue
                if path.name.startswith("tests") or path.suffix not in {".py", ".html", ".yaml", ".css", ".js", ".svg", ".png", ".jpg", ".json"}:
                    continue
                entry = ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
    for name in ["index.html", "shell.js", "worker.js", "storage.js", "manifest.webmanifest", "icon.svg"]:
        shutil.copyfile(ROOT / "pwa" / name, output / name)
    for folder in [ROOT / "referentiel/static", ROOT / "suivi/static"]:
        shutil.copytree(folder, output / "static", dirs_exist_ok=True)
    build = hashlib.sha256()
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {"sw.js", "config.json"}:
            build.update(path.relative_to(output).as_posix().encode())
            build.update(path.read_bytes())
    version = "pwa-prototype." + build.hexdigest()[:16]
    (output / "sw.js").write_text((ROOT / "pwa/sw.js").read_text().replace("__BUILD__", version))
    assets = [{"url": "/" + path.relative_to(output).as_posix(),
               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
              for path in sorted(output.rglob("*")) if path.is_file() and path.name != "config.json"]
    config = {"version": version, "pyodide": PYODIDE, "testMode": args.test,
              "wheels": sorted(path.name for path in wheels.glob("*.whl")), "assets": assets}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"Prototype construit : {output} ({version}, {sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) / 1024**2:.1f} Mio non compressés)")


if __name__ == "__main__":
    main()
