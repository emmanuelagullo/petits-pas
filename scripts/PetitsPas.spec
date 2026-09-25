# -*- mode: python ; coding: utf-8 -*-
"""Construire un dossier autonome sur le système où tourne PyInstaller."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH peut désigner la racine du dépôt ou le dossier du .spec selon
# la manière dont PyInstaller a été invoqué.
racine = next(
    (chemin for chemin in (Path(SPECPATH).resolve(), Path(SPECPATH).resolve().parent)
     if (chemin / "scripts" / "lancer-local.py").is_file()),
    None,
)
if racine is None:
    raise FileNotFoundError(f"Lanceur introuvable depuis le dossier PyInstaller : {SPECPATH}")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carnet.settings")

donnees = [
    (str(racine / "suivi" / "templates"), "suivi/templates"),
    (str(racine / "suivi" / "static"), "suivi/static"),
    (str(racine / "referentiel"), "referentiel"),
]
donnees += collect_data_files("django.contrib.admin", includes=["templates/**", "static/**"])

imports = [
    "carnet.settings", "carnet.urls", "carnet.wsgi",
    # Django importe ces modules via des chaînes dans MIDDLEWARE et STORAGES.
    "whitenoise.middleware", "whitenoise.storage",
]
imports += collect_submodules("comptes", filter=lambda nom: not nom.endswith(".tests"))
imports += collect_submodules("suivi", filter=lambda nom: not nom.endswith(".tests"))
if os.name == "nt":
    imports += ["webview.platforms.winforms", "webview.platforms.edgechromium"]
    donnees += collect_data_files("webview", includes=["lib/**"])
else:
    imports += ["webview.platforms.gtk"]

analyse = Analysis(
    [str(racine / "scripts" / "lancer-local.py")],
    pathex=[str(racine)],
    binaries=[],
    datas=donnees,
    hiddenimports=imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["gunicorn", "psycopg", "storages", "boto3", "botocore"],
    noarchive=False,
)
archive = PYZ(analyse.pure)
programme = EXE(
    archive,
    analyse.scripts,
    [],
    exclude_binaries=True,
    name="PetitsPas",
    console=True,  # Une console permet de diagnostiquer la première version Windows.
)
collation = COLLECT(
    programme,
    analyse.binaries,
    analyse.datas,
    strip=False,
    upx=False,
    name="PetitsPas",
)
