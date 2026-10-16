# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from pas_communs.construction import assembler

racine = next((p for p in (Path(SPECPATH).resolve(), Path(SPECPATH).resolve().parent)
    if (p / "scripts/lancer-local.py").is_file()), None)
if racine is None:
    raise FileNotFoundError(f"Lanceur introuvable depuis {SPECPATH}")
collation = assembler(racine, globals(), nom="PetitsPas", settings="carnet.settings",
    ressources=[("version-application.txt", "."), ("suivi/templates", "suivi/templates"),
                ("suivi/static", "suivi/static"), ("referentiel", "referentiel")],
    paquets=["comptes", "suivi"], paquets_ressources=["django.contrib.admin"],
    imports=["carnet.settings", "carnet.urls", "carnet.wsgi", "whitenoise.middleware", "whitenoise.storage"],
    pango_variable="PETITS_PAS_PANGO_BIN",
    exclusions=["gunicorn", "psycopg", "storages", "boto3", "botocore"])
