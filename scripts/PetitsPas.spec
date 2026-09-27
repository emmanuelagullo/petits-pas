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
    pango_bin = os.environ.get("PETITS_PAS_PANGO_BIN")
    if not pango_bin:
        raise RuntimeError("Définir PETITS_PAS_PANGO_BIN vers le dossier UCRT64/bin de MSYS2.")
    dossier_pango = Path(pango_bin)
    bibliotheques_pango = [
        "libgobject-2.0-0.dll", "libpango-1.0-0.dll",
        "libpangoft2-1.0-0.dll", "libharfbuzz-0.dll",
        "libharfbuzz-subset-0.dll", "libfontconfig-1.dll",
    ]
    manquantes = [nom for nom in bibliotheques_pango if not (dossier_pango / nom).is_file()]
    if manquantes:
        raise FileNotFoundError(f"DLL Windows manquantes dans {dossier_pango} : {manquantes}")
    # PyInstaller analyse les dépendances transitives de ces DLL et les place
    # dans _internal ; WeasyPrint les cherchera dans ce dossier au lancement.
    binaires = [(str(dossier_pango / nom), ".") for nom in bibliotheques_pango]
else:
    binaires = []
    imports += ["webview.platforms.gtk", "gi.repository.Gtk", "gi.repository.WebKit2"]
    # PyInstaller ne voit pas les imports dynamiques de PyWebView. Sur Guix,
    # les typelibs WebKit sont fournis par GI_TYPELIB_PATH et non par Python.
    chemins_typelibs = [Path(chemin) for chemin in os.environ.get("GI_TYPELIB_PATH", "").split(os.pathsep) if chemin]
    chemins_typelibs += [Path("/usr/lib/x86_64-linux-gnu/girepository-1.0"), Path("/usr/lib/girepository-1.0")]
    for version in ("4.1", "4.0"):
        typelib = next((dossier / f"WebKit2-{version}.typelib" for dossier in chemins_typelibs if (dossier / f"WebKit2-{version}.typelib").is_file()), None)
        if typelib:
            donnees.append((str(typelib), "gi_typelibs"))

analyse = Analysis(
    [str(racine / "scripts" / "lancer-local.py")],
    pathex=[str(racine)],
    binaries=binaires,
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
