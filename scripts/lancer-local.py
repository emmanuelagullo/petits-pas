#!/usr/bin/env python3
"""Ouvrir le Django existant dans une fenêtre locale PyWebView (#L1)."""

import argparse
import os
import secrets
import sys
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import Thread
from wsgiref.simple_server import WSGIServer, make_server


class ServeurLocal(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = False


def main():
    projet = Path(__file__).resolve().parent.parent
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--paquet",
        type=Path,
        default=Path(
            os.environ.get("PETITS_PAS_PAQUET_AUTONOME", projet / "paquet-autonome")
        ),
        help="répertoire des données autonomes (défaut : ./paquet-autonome)",
    )
    arguments = analyseur.parse_args()
    paquet = arguments.paquet.expanduser().resolve()
    if paquet == projet:
        raise SystemExit(
            "Le paquet autonome doit être un répertoire distinct du projet."
        )

    os.chdir(projet)
    sys.path.insert(0, str(projet))

    if os.environ.get("DATABASE_URL") or os.environ.get("CARNET_S3_BUCKET"):
        raise SystemExit("Le mode local requiert SQLite et les médias sur disque.")
    if os.environ.get("CARNET_ENVIRONNEMENT_EPHEMERE") == "oui":
        raise SystemExit("Le mode local ne peut pas utiliser la démonstration jetable.")

    # Un paquet regroupe la base, les médias et la clé des sessions. Il ne
    # reprend jamais implicitement la base de développement située à la racine.
    os.umask(0o077)
    paquet.mkdir(parents=True, exist_ok=True)
    (paquet / "media").mkdir(exist_ok=True)
    chemin_cle = paquet / "secret-key"
    try:
        with chemin_cle.open("x", encoding="utf-8") as fichier:
            fichier.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    cle = chemin_cle.read_text(encoding="utf-8").strip()
    if not cle:
        raise SystemExit(f"Clé locale vide : {chemin_cle}")

    os.environ["CARNET_DEBUG"] = "0"
    os.environ["CARNET_HOSTS"] = "127.0.0.1,localhost"
    os.environ["CARNET_EMAIL_DESACTIVE"] = "oui"
    os.environ.pop("CARNET_EMAIL_BACKEND", None)
    os.environ["CARNET_SECRET_KEY"] = cle
    os.environ["CARNET_SQLITE_PATH"] = str(paquet / "carnet.sqlite3")
    os.environ["CARNET_MEDIA_ROOT"] = str(paquet / "media")
    os.environ["DJANGO_SETTINGS_MODULE"] = "carnet.settings"

    try:
        import webview
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
    except ImportError as exc:
        raise SystemExit(
            "Dépendance absente : installez requirements.txt et "
            "requirements-local.txt."
        ) from exc

    # StaticFilesHandler sert les fichiers du dépôt pendant ce prototype,
    # sans dépendre de collectstatic ni modifier la configuration partagée.
    application = StaticFilesHandler(get_wsgi_application())
    call_command("migrate", interactive=False, verbosity=0)
    serveur = make_server("127.0.0.1", 0, application, server_class=ServeurLocal)
    thread = Thread(target=serveur.serve_forever, name="petits-pas-local", daemon=True)
    thread.start()
    try:
        webview.create_window(
            "Petits Pas", f"http://127.0.0.1:{serveur.server_port}/"
        )
        webview.start()
    finally:
        serveur.shutdown()
        thread.join(timeout=5)
        serveur.server_close()


if __name__ == "__main__":
    main()
