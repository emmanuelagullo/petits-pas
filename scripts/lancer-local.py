#!/usr/bin/env python3
"""Ouvrir le Django existant dans une fenêtre locale PyWebView (#L1)."""

import argparse
import ctypes
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import Event, RLock, Thread
import traceback
from urllib.request import urlopen
from wsgiref.simple_server import WSGIServer, make_server

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class ServeurLocal(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = False


def paquet_par_defaut():
    if os.name == "nt":
        racine = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        racine = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return racine.expanduser() / "petits-pas" / "paquet-autonome"


@contextmanager
def verrouiller(paquet):
    # Le verrou doit survivre au renommage du paquet lors d'une restauration.
    with (paquet.parent / f".{paquet.name}.verrou").open("a+b") as verrou:
        try:
            if os.name == "nt":
                verrou.seek(0)
                if not verrou.read(1):
                    verrou.seek(0)
                    verrou.write(b"\0")
                    verrou.flush()
                verrou.seek(0)
                msvcrt.locking(verrou.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise SystemExit(f"Ce paquet est déjà ouvert : {paquet}") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                verrou.seek(0)
                msvcrt.locking(verrou.fileno(), msvcrt.LK_UNLCK, 1)
            else:
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
            with closing(sqlite3.connect(source / "carnet.sqlite3")) as ancienne:
                with closing(sqlite3.connect(temporaire / "carnet.sqlite3")) as nouvelle:
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
    # Une ancienne configuration serveur ne doit pas masquer la version du programme installé.
    os.environ.pop("CARNET_VERSION", None)
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
    if os.name == "nt" and getattr(sys, "frozen", False):
        # _MEIPASS est le dossier _internal du paquet PyInstaller.
        bibliotheques = Path(sys._MEIPASS)
        if (bibliotheques / "libgobject-2.0-0.dll").is_file():
            os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(bibliotheques)


def migration_necessaire(paquet):
    """Repérer un schéma existant à faire évoluer avant d'ouvrir la progression."""
    base = paquet / "carnet.sqlite3"
    if not base.is_file():
        return False
    with closing(sqlite3.connect(base)) as connexion:
        if not connexion.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'django_migrations'"
        ).fetchone():
            return False
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executeur = MigrationExecutor(connection)
    return bool(executeur.migration_plan(executeur.loader.graph.leaf_nodes()))


def proteger_avant_migration(paquet):
    """Copier la base avant de modifier son schéma."""
    base = paquet / "carnet.sqlite3"
    sauvegardes = paquet / "sauvegardes-migrations"
    sauvegardes.mkdir(exist_ok=True)
    chemin = sauvegardes / f"avant-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite3"
    with closing(sqlite3.connect(base)) as origine, closing(sqlite3.connect(chemin)) as copie:
        origine.backup(copie)
        if copie.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            chemin.unlink()
            raise RuntimeError("La sauvegarde avant migration est invalide.")
    print(f"Copie de la base avant migration : {chemin}")


@contextmanager
def progression_migration():
    """Informer pendant une migration Windows sans exposer une console."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    titre = "Petits Pas — mise à jour de l'école"
    fenetre = ctypes.windll.user32
    # Les handles Windows sont des pointeurs 64 bits sur les postes x64.
    fenetre.FindWindowW.restype = ctypes.c_void_p
    fenetre.GetDlgItem.argtypes = (ctypes.c_void_p, ctypes.c_int)
    fenetre.EnableWindow.argtypes = (ctypes.c_void_p, ctypes.c_bool)
    fenetre.GetSystemMenu.argtypes = (ctypes.c_void_p, ctypes.c_bool)
    fenetre.GetSystemMenu.restype = ctypes.c_void_p
    fenetre.EnableMenuItem.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)
    fenetre.DrawMenuBar.argtypes = (ctypes.c_void_p,)
    fenetre.PostMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    fil = Thread(
        target=fenetre.MessageBoxW,
        args=(None, "Mise à jour de l'école en cours. Merci de patienter.", titre, 0),
        daemon=True,
    )
    fil.start()
    handle = None
    for _ in range(30):
        handle = fenetre.FindWindowW(None, titre)
        if handle:
            # MessageBox affiche normalement « OK ». Neutraliser ce bouton
            # et la fermeture système pour toute la durée de l'opération.
            fenetre.EnableWindow(fenetre.GetDlgItem(handle, 1), False)
            menu = fenetre.GetSystemMenu(handle, False)
            fenetre.EnableMenuItem(menu, 0xF060, 0x0001)  # SC_CLOSE, MF_GRAYED
            fenetre.DrawMenuBar(handle)
            break
        time.sleep(0.1)
    try:
        yield
    finally:
        if handle:
            fenetre.PostMessageW(handle, 0x10, 0, 0)  # WM_CLOSE
        fil.join(timeout=1)


def verifier_distribution(projet):
    """Contrôler les ressources nécessaires avant toute création de paquet."""
    import django
    import webview
    from django.core.management import call_command
    from django.contrib.staticfiles import finders
    from django.core.files.storage import storages
    from django.template.loader import get_template
    from django.core.wsgi import get_wsgi_application

    django.setup()
    call_command("check")
    get_wsgi_application()  # Vérifie les middlewares chargés par leur nom.
    storages["staticfiles"]  # Vérifie le backend avant collectstatic.
    get_template("suivi/connexion.html")
    if not finders.find("suivi/carnet.css"):
        raise SystemExit("La feuille de style est absente de la distribution.")
    if not (projet / "referentiel" / "trame-cycle1.yaml").is_file():
        raise SystemExit("La trame pédagogique est absente de la distribution.")
    if getattr(sys, "frozen", False) and not (projet / "referentiel/demo/ecole-fictive.zip").is_file():
        raise SystemExit("L'école fictive est absente de la distribution.")
    if os.name == "nt":
        # L'import de webview seul ne charge pas pythonnet. Vérifier ici la
        # passerelle .NET réellement utilisée au démarrage sous Windows.
        import clr  # noqa: F401
        if getattr(sys, "frozen", False):
            for nom in ("libgobject-2.0-0.dll", "libglib-2.0-0.dll", "libpango-1.0-0.dll"):
                if not (Path(sys._MEIPASS) / nom).is_file():
                    raise RuntimeError(f"Bibliothèque PDF absente du paquet Windows : {nom}")
        from weasyprint import HTML

        pdf = HTML(string="<p>Vérification PDF Petits Pas</p>").write_pdf()
        if not pdf.startswith(b"%PDF-"):
            raise RuntimeError("Le paquet Windows ne produit pas de PDF.")
    else:
        import gi

        try:
            gi.require_version("WebKit2", "4.1")
        except ValueError:
            try:
                gi.require_version("WebKit2", "4.0")
            except ValueError as exc:
                raise SystemExit(
                    "WebKit2 (4.1 ou 4.0) est absent du paquet ou de la machine. "
                    "Vérifiez GI_TYPELIB_PATH lors de la construction et installez WebKitGTK."
                ) from exc
        from gi.repository import Gtk, WebKit2  # noqa: F401

    print(f"Django {django.get_version()} et PyWebView : distribution vérifiée.")


def choisir_paquet(habituel, defaut, essai=False):
    habituel = Path(habituel).expanduser().resolve()
    destination = Path(defaut).parent / "essai-fictif"
    if destination.is_symlink() or destination.resolve() == habituel:
        raise ValueError("L'espace d'essai doit être distinct du paquet habituel, sans lien symbolique.")
    return destination.resolve() if essai else habituel


def arguments_espace(arguments, espace, dossier=None):
    resultat = []
    iterator = iter(arguments)
    for argument in iterator:
        if argument == "--apercu":
            next(iterator, None)
        elif argument.startswith("--apercu="):
            continue
        elif argument != "--essai":
            resultat.append(argument)
    if espace == "essai":
        resultat.append("--essai")
    elif espace == "apercu":
        resultat.extend(["--apercu", str(dossier)])
    return resultat


def main():
    projet = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
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
    analyseur.add_argument(
        "--verifier-distribution", action="store_true",
        help="contrôler les modules, modèles et ressources sans créer de paquet",
    )
    analyseur.add_argument("--essai", action="store_true",
        help="ouvrir l'école fictive dans un dossier distinct, sans toucher au paquet habituel")
    analyseur.add_argument("--apercu", type=Path, help="rouvrir une copie ZIP déjà vérifiée par Petits Pas")
    arguments = analyseur.parse_args()
    if arguments.apercu and (arguments.essai or arguments.creer_ecole or arguments.charger_referentiel
                            or arguments.copier_paquet or arguments.deplacer_paquet):
        analyseur.error("--apercu ne se combine pas avec un autre espace ou une opération sur les données")
    if arguments.essai and (arguments.creer_ecole or arguments.charger_referentiel
                           or arguments.copier_paquet or arguments.deplacer_paquet):
        analyseur.error("--essai ne se combine pas avec une opération sur les données")
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
    try:
        paquet = choisir_paquet(arguments.paquet, defaut, arguments.essai)
        if arguments.apercu:
            sys.path.insert(0, str(projet))
            from suivi.apercu_local import verifier_dossier
            paquet = verifier_dossier(arguments.apercu, arguments.paquet, defaut.parent / "essai-fictif")
    except (ValueError, OSError) as erreur:
        raise SystemExit(str(erreur)) from erreur
    os.environ["CARNET_ESPACE_ESSAI"] = "oui" if arguments.essai else "non"
    os.environ["CARNET_ESPACE_APERCU"] = "oui" if arguments.apercu else "non"
    if paquet == projet:
        raise SystemExit(
            "Le paquet autonome doit être un répertoire distinct du projet."
        )

    if os.environ.get("DATABASE_URL") or os.environ.get("CARNET_S3_BUCKET"):
        raise SystemExit("Le mode local requiert SQLite et les médias sur disque.")
    if os.environ.get("CARNET_ENVIRONNEMENT_EPHEMERE") == "oui":
        raise SystemExit("Le mode local ne peut pas utiliser la démonstration jetable.")

    os.umask(0o077)
    if arguments.verifier_distribution:
        os.chdir(projet)
        sys.path.insert(0, str(projet))
        configurer_environnement(paquet, "verification-distribution")
        os.environ["CARNET_SQLITE_PATH"] = ":memory:"
        verifier_distribution(projet)
        return
    if destination_demande:
        destination = destination_demande.expanduser().resolve()
        if paquet == destination:
            analyseur.error("la source et la destination sont identiques")
        copier_paquet(paquet, destination)
        return
    if not paquet.exists():
        precedents = sorted(paquet.parent.glob(f".{paquet.name}-avant-restauration-*"))
        if precedents:
            raise SystemExit(
                f"Paquet absent : {paquet}. Une restauration a peut-être été interrompue.\n"
                f"Paquet(s) précédent(s) conservé(s) : {', '.join(map(str, precedents))}\n"
                "Vérifiez ces dossiers avant de relancer ou de restaurer depuis un ZIP."
            )
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
    if arguments.essai and not (paquet / "carnet.sqlite3").exists():
        from suivi.essai_local import installer_ecole_fictive
        archive = projet / "referentiel/demo/ecole-fictive.zip"
        if not archive.exists():
            raise SystemExit("L'école fictive manque. Depuis les sources, lancez scripts/construire-ecole-fictive.py.")
        installer_ecole_fictive(archive, paquet)
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
        redemarrer = executer(paquet, projet, arguments)
    if redemarrer:
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
        else:
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])


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
    migration = migration_necessaire(paquet)
    if migration:
        with progression_migration():
            proteger_avant_migration(paquet)
            call_command("migrate", interactive=False, verbosity=0)
        print("Mise à jour de l'école terminée.")
        if os.name == "nt" and getattr(sys, "frozen", False):
            ctypes.windll.user32.MessageBoxW(
                None, "La mise à jour de l'école est terminée. Petits Pas va s'ouvrir.",
                "Petits Pas", 0x40,
            )
    else:
        call_command("migrate", interactive=False, verbosity=0)
    referentiel = projet / "referentiel" / "trame-cycle1.yaml"
    if arguments.creer_ecole:
        from suivi.models import Ecole

        if Ecole.objects.exists():
            raise SystemExit("Ce paquet contient déjà une école.")
        call_command("creer_ecole", arguments.creer_ecole, commune=arguments.commune)
        call_command("charger_referentiel", str(referentiel))
        from suivi.services.reprise_referentiels import preparer_nouvelle_ecole
        preparer_nouvelle_ecole(Ecole.objects.get())
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
    from suivi.paquet_local import annuler_preparation, appliquer_restauration, restauration_en_attente

    requetes = RLock()
    redemarrage_demande = Event()
    fenetre = None

    class CommandesFenetre:
        def appliquer_et_redemarrer(self):
            # L'API JS n'a accès à cette commande qu'après confirmation Django.
            if restauration_en_attente() is None or fenetre is None:
                return False
            redemarrage_demande.set()
            fenetre.destroy()
            return True

        def changer_espace(self, espace):
            if espace not in {"essai", "habituel"} or fenetre is None or restauration_en_attente() is not None:
                return False
            with requetes:
                # Les chemins ne viennent jamais de l'écran ; seul le drapeau change.
                sys.argv[:] = arguments_espace(sys.argv, espace)
                redemarrage_demande.set()
                fenetre.destroy()
                return True

        def ouvrir_apercu(self):
            from suivi import apercu_local
            with requetes:
                if fenetre is None or restauration_en_attente() is not None or not apercu_local.ouverture_demandee():
                    return False
                copie = apercu_local.detacher()
                sys.argv[:] = arguments_espace(sys.argv, "apercu", copie.etape)
                redemarrage_demande.set()
                fenetre.destroy()
                return True

        def reprendre_apercu(self):
            from suivi import apercu_local
            with requetes:
                if fenetre is None or restauration_en_attente() is not None or apercu_local.preparation() is not None:
                    return False
                dossier = apercu_local.derniere_copie(paquet.parent, arguments.paquet,
                    paquet_par_defaut().parent / "essai-fictif")
                if dossier is None:
                    return False
                sys.argv[:] = arguments_espace(sys.argv, "apercu", dossier)
                redemarrage_demande.set()
                fenetre.destroy()
                return True

    commandes = CommandesFenetre()

    def application_locale(environ, start_response):
        # Un export attend la fin des écritures en cours, y compris les médias.
        with requetes:
            if (
                restauration_en_attente() is not None
                and environ.get("REQUEST_METHOD") not in {"GET", "HEAD", "OPTIONS"}
            ):
                start_response("423 Locked", [("Content-Type", "text/plain; charset=utf-8")])
                yield "Restauration prête : appliquez et redémarrez Petits Pas.\n".encode("utf-8")
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
        # PyWebView désactive les téléchargements par défaut. Sans cette
        # option, une réponse ZIP valide n'ouvre aucune boîte d'enregistrement.
        webview.settings["ALLOW_DOWNLOADS"] = True
        try:
            with urlopen(
                f"http://127.0.0.1:{serveur.server_port}/static/suivi/carnet.css",
                timeout=5,
            ) as reponse:
                if "text/css" not in reponse.headers.get("Content-Type", ""):
                    raise RuntimeError("Le CSS local n'est pas servi correctement.")
        except Exception as exc:
            raise SystemExit(f"Échec du chargement du CSS local : {exc}") from exc
        # Ne pas placer l'objet fenêtre sur js_api : PyWebView parcourt les
        # attributs publics de cet objet et récursait dans fenetre.native.
        fenetre = webview.create_window(
            "Petits Pas — ZIP à vérifier" if arguments.apercu else ("Petits Pas — espace d’essai" if arguments.essai else "Petits Pas"), f"http://127.0.0.1:{serveur.server_port}/",
            js_api=commandes,
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
        else:
            annuler_preparation()
        from suivi import apercu_local
        apercu_local.annuler()
    return redemarrage_demande.is_set()


def afficher_erreur_windows(message):
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, message, "Petits Pas", 0x10)


def demarrer_windows():
    """Conserver le diagnostic sans console, y compris en cas d'échec initial."""
    journal = paquet_par_defaut().parent / "logs" / "dernier-demarrage.log"
    interactif = "--verifier-distribution" not in sys.argv
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        sortie = journal.open("w", encoding="utf-8", buffering=1)
    except OSError as exc:
        if interactif:
            afficher_erreur_windows(
                "Petits Pas n'a pas pu démarrer et n'a pas pu écrire son journal.\n\n"
                f"Emplacement prévu : {journal}\nErreur : {exc}"
            )
        raise SystemExit(1) from exc
    with sortie, redirect_stdout(sortie), redirect_stderr(sortie):
        try:
            main()
        except SystemExit as exc:
            if exc.code is None or exc.code == 0:
                return
            traceback.print_exc()
            if interactif:
                afficher_erreur_windows(
                    "Petits Pas n'a pas pu démarrer.\n\n"
                    f"Un diagnostic a été enregistré ici :\n{journal}"
                )
            raise
        except Exception:
            traceback.print_exc()
            if interactif:
                afficher_erreur_windows(
                    "Petits Pas n'a pas pu démarrer.\n\n"
                    f"Un diagnostic a été enregistré ici :\n{journal}"
                )
            raise SystemExit(1)


if __name__ == "__main__":
    if os.name == "nt" and getattr(sys, "frozen", False):
        demarrer_windows()
    else:
        main()
