#!/usr/bin/env python3
"""Ouvrir le Django existant dans une fenêtre locale PyWebView (#L1)."""

import argparse
import fcntl
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import RLock, Thread
from urllib.request import urlopen
from wsgiref.simple_server import WSGIServer, make_server


class ServeurLocal(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = False


def paquet_par_defaut():
    racine = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return racine.expanduser() / "petits-pas" / "paquet-autonome"


@contextmanager
def verrouiller(paquet):
    # Le verrou doit survivre au renommage du paquet lors d'une restauration.
    with (paquet.parent / f".{paquet.name}.verrou").open("a+b") as verrou:
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f"Ce paquet est déjà ouvert : {paquet}") from exc
        try:
            yield
        finally:
            fcntl.flock(verrou, fcntl.LOCK_UN)


def copier_paquet(source, destination):
    if not (source / "carnet.sqlite3").is_file() or not (source / "secret-key").is_file():
        raise SystemExit(f"Paquet source incomplet : {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SystemExit(f"Destination déjà présente : {destination}")
    with verrouiller(source):
        temporaire = Path(tempfile.mkdtemp(prefix=".paquet-autonome-", dir=destination.parent))
        try:
            shutil.copy2(source / "secret-key", temporaire / "secret-key")
            if (source / "media").is_dir():
                shutil.copytree(source / "media", temporaire / "media")
            else:
                (temporaire / "media").mkdir()
            with sqlite3.connect(source / "carnet.sqlite3") as ancienne:
                with sqlite3.connect(temporaire / "carnet.sqlite3") as nouvelle:
                    ancienne.backup(nouvelle)
                    if nouvelle.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise RuntimeError("La copie SQLite ne passe pas le contrôle d'intégrité.")
            temporaire.rename(destination)
        finally:
            if temporaire.exists():
                shutil.rmtree(temporaire)
    print(f"Paquet copié : {destination}")
    print(f"L'original a été conservé : {source}")


def configurer_environnement(paquet, cle):
    os.environ["CARNET_DEBUG"] = "0"
    os.environ["CARNET_MODE_LOCAL"] = "oui"
    os.environ["CARNET_HOSTS"] = "127.0.0.1,localhost"
    os.environ["CARNET_EMAIL_DESACTIVE"] = "oui"
    os.environ.pop("CARNET_EMAIL_BACKEND", None)
    os.environ["CARNET_SECRET_KEY"] = cle
    os.environ["CARNET_SQLITE_PATH"] = str(paquet / "carnet.sqlite3")
    os.environ["CARNET_MEDIA_ROOT"] = str(paquet / "media")
    os.environ["CARNET_STATIC_ROOT"] = str(paquet / "staticfiles")
    os.environ["CARNET_STATIC_URL"] = "/static/"
    os.environ["DJANGO_SETTINGS_MODULE"] = "carnet.settings"


def proteger_avant_migration(paquet):
    """Conserver la base précédente seulement si le schéma doit changer."""
    base = paquet / "carnet.sqlite3"
    if not base.is_file():
        return
    with sqlite3.connect(base) as connexion:
        if not connexion.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'django_migrations'"
        ).fetchone():
            return
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executeur = MigrationExecutor(connection)
    if not executeur.migration_plan(executeur.loader.graph.leaf_nodes()):
        return
    sauvegardes = paquet / "sauvegardes-migrations"
    sauvegardes.mkdir(exist_ok=True)
    chemin = sauvegardes / f"avant-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite3"
    with sqlite3.connect(base) as origine, sqlite3.connect(chemin) as copie:
        origine.backup(copie)
        if copie.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            chemin.unlink()
            raise RuntimeError("La sauvegarde avant migration est invalide.")
    print(f"Copie de la base avant migration : {chemin}")


def main():
    projet = Path(__file__).resolve().parent.parent
    ancien_paquet = projet / "paquet-autonome"
    defaut = paquet_par_defaut()
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--paquet",
        type=Path,
        default=Path(
            os.environ.get("PETITS_PAS_PAQUET_AUTONOME", defaut)
        ),
        help=f"répertoire des données autonomes (défaut : {defaut})",
    )
    analyseur.add_argument(
        "--copier-paquet", type=Path, metavar="DESTINATION",
        help="copier le paquet choisi vers DESTINATION, puis quitter",
    )
    analyseur.add_argument(
        "--deplacer-paquet", type=Path, metavar="DESTINATION",
        help=argparse.SUPPRESS,
    )
    analyseur.add_argument(
        "--creer-ecole",
        metavar="NOM",
        help="initialiser une école et ses comptes dans ce paquet, puis quitter",
    )
    analyseur.add_argument("--commune", default="", help="commune de l'école créée")
    analyseur.add_argument(
        "--charger-referentiel",
        action="store_true",
        help="charger la trame pédagogique provisoire dans l'école existante, puis quitter",
    )
    arguments = analyseur.parse_args()
    if arguments.commune and not arguments.creer_ecole:
        analyseur.error("--commune nécessite --creer-ecole")
    if arguments.creer_ecole and arguments.charger_referentiel:
        analyseur.error("--creer-ecole charge déjà le référentiel")
    destination_demande = arguments.copier_paquet or arguments.deplacer_paquet
    if arguments.copier_paquet and arguments.deplacer_paquet:
        analyseur.error("choisissez une seule option de copie")
    if destination_demande and (
        arguments.creer_ecole or arguments.charger_referentiel or arguments.commune
    ):
        analyseur.error("--copier-paquet ne se combine pas avec l'initialisation")
    paquet = arguments.paquet.expanduser().resolve()
    if paquet == projet:
        raise SystemExit(
            "Le paquet autonome doit être un répertoire distinct du projet."
        )

    if os.environ.get("DATABASE_URL") or os.environ.get("CARNET_S3_BUCKET"):
        raise SystemExit("Le mode local requiert SQLite et les médias sur disque.")
    if os.environ.get("CARNET_ENVIRONNEMENT_EPHEMERE") == "oui":
        raise SystemExit("Le mode local ne peut pas utiliser la démonstration jetable.")

    os.umask(0o077)
    if destination_demande:
        destination = destination_demande.expanduser().resolve()
        if paquet == destination:
            analyseur.error("la source et la destination sont identiques")
        copier_paquet(paquet, destination)
        return
    if (
        paquet == defaut.resolve() and not (paquet / "carnet.sqlite3").exists()
        and ancien_paquet.is_dir()
    ):
        raise SystemExit(
            f"Un paquet existe déjà dans le dépôt : {ancien_paquet}\n"
            f"Copiez-le avec : python scripts/lancer-local.py --paquet "
            f"{ancien_paquet} --copier-paquet {paquet}"
        )
    if paquet.exists() and (paquet / "secret-key").exists() != (paquet / "carnet.sqlite3").exists():
        raise SystemExit(f"Paquet incomplet (base ou clé manquante) : {paquet}")

    os.chdir(projet)
    sys.path.insert(0, str(projet))
    # Un paquet regroupe la base, les médias et la clé des sessions.
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

    with verrouiller(paquet):
        configurer_environnement(paquet, cle)
        executer(paquet, projet, arguments)


def executer(paquet, projet, arguments):
    try:
        import django
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
    except ImportError as exc:
        raise SystemExit(
            f"Dépendance Python absente : {exc}. Vérifiez l'environnement du projet."
        ) from exc

    # Avec DEBUG désactivé, WhiteNoise lit les fichiers collectés au moment
    # de la construction de l'application WSGI. Collecter d'abord et isoler
    # cette sortie du staticfiles des autres profils du projet.
    django.setup()
    call_command("collectstatic", interactive=False, verbosity=0)
    application = get_wsgi_application()
    proteger_avant_migration(paquet)
    call_command("migrate", interactive=False, verbosity=0)
    referentiel = projet / "referentiel" / "trame-cycle1.yaml"
    if arguments.creer_ecole:
        from suivi.models import Ecole

        if Ecole.objects.exists():
            raise SystemExit("Ce paquet contient déjà une école.")
        call_command("creer_ecole", arguments.creer_ecole, commune=arguments.commune)
        call_command("charger_referentiel", str(referentiel))
        return
    if arguments.charger_referentiel:
        call_command("charger_referentiel", str(referentiel))
        return

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            f"PyWebView est absent : {exc}. Installez requirements-local.txt."
        ) from exc
    from suivi.paquet_local import appliquer_restauration, restauration_en_attente

    requetes = RLock()

    def application_locale(environ, start_response):
        # Un export attend la fin des écritures en cours, y compris les médias.
        with requetes:
            if (
                restauration_en_attente() is not None
                and environ.get("REQUEST_METHOD") not in {"GET", "HEAD", "OPTIONS"}
            ):
                start_response("423 Locked", [("Content-Type", "text/plain; charset=utf-8")])
                yield "Restauration prête : fermez la fenêtre Petits Pas.\n".encode("utf-8")
                return
            iterable = application(environ, start_response)
            try:
                yield from iterable
            finally:
                if hasattr(iterable, "close"):
                    iterable.close()

    serveur = make_server("127.0.0.1", 0, application_locale, server_class=ServeurLocal)
    thread = Thread(target=serveur.serve_forever, name="petits-pas-local", daemon=True)
    thread.start()
    try:
        try:
            with urlopen(
                f"http://127.0.0.1:{serveur.server_port}/static/suivi/carnet.css",
                timeout=5,
            ) as reponse:
                if "text/css" not in reponse.headers.get("Content-Type", ""):
                    raise RuntimeError("Le CSS local n'est pas servi correctement.")
        except Exception as exc:
            raise SystemExit(f"Échec du chargement du CSS local : {exc}") from exc
        webview.create_window(
            "Petits Pas", f"http://127.0.0.1:{serveur.server_port}/"
        )
        webview.start()
    finally:
        serveur.shutdown()
        thread.join(timeout=5)
        serveur.server_close()
        etape = restauration_en_attente()
        if etape is not None:
            with requetes:
                from django.db import connections

                connections.close_all()
                ancien = appliquer_restauration(paquet, etape)
                print(f"Restauration appliquée. Paquet précédent conservé : {ancien}")


if __name__ == "__main__":
    main()
