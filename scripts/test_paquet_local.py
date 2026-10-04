"""Contrôles des opérations sur les données autonomes, sans Django ni GTK."""

import importlib.util
import os
import subprocess
from contextlib import closing
import sqlite3
import sys
from threading import Event
from types import SimpleNamespace
from types import ModuleType
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from suivi.paquet_local import (
    annuler_preparation,
    appliquer_restauration,
    confirmer_restauration,
    creer_sauvegarde,
    lire_resultat,
    noter_export,
    suivi_export,
    SUIVI_SAUVEGARDE,
    preparer_restauration,
    preparation_en_attente,
    retenir_preparation,
)


spec = importlib.util.spec_from_file_location(
    "lancer_local", Path(__file__).with_name("lancer-local.py")
)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class PaquetLocalTests(unittest.TestCase):
    def test_suivi_export_recent_ancien_absent_ou_altere(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as temp:
            paquet = Path(temp)
            self.assertTrue(suivi_export(paquet)["rappel_sauvegarde_local"])
            noter_export(paquet)
            recent = suivi_export(paquet)
            self.assertFalse(recent["rappel_sauvegarde_local"])
            self.assertTrue(suivi_export(paquet, recent["dernier_export_local"] + timedelta(days=8))["rappel_sauvegarde_local"])
            for content in ['invalide', '{"prepare_le": null}', '{"prepare_le": "2099-01-01T00:00:00+00:00"}']:
                (paquet / SUIVI_SAUVEGARDE).write_text(content)
                self.assertIsNone(suivi_export(paquet)["dernier_export_local"])

    def test_suivi_export_absent_du_zip_et_de_la_restauration(self):
        with tempfile.TemporaryDirectory() as temp:
            paquet = Path(temp) / 'paquet'
            paquet.mkdir()
            (paquet / 'media').mkdir()
            (paquet / 'secret-key').write_text('cle-entierement-fictive')
            with closing(sqlite3.connect(paquet / 'carnet.sqlite3')) as db, db:
                db.execute('CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT, applied TEXT)')
            noter_export(paquet)
            output = BytesIO()
            creer_sauvegarde(paquet, output)
            with ZipFile(output) as archive:
                self.assertNotIn(SUIVI_SAUVEGARDE, archive.namelist())
            output.seek(0)
            etape = preparer_restauration(output, Path(temp))
            self.assertIsNone(suivi_export(etape.etape)["dernier_export_local"])

    def test_progression_windows_reste_visible_pendant_la_copie_et_la_migration(self):
        fermeture = Event()
        fenetre = MagicMock()
        fenetre.FindWindowW.return_value = 1234
        fenetre.GetDlgItem.return_value = 5678
        fenetre.MessageBoxW.side_effect = lambda *args: fermeture.wait(2)
        fenetre.PostMessageW.side_effect = lambda *args: fermeture.set()
        windows = SimpleNamespace(windll=SimpleNamespace(user32=fenetre),
                                  c_void_p=local.ctypes.c_void_p,
                                  c_int=local.ctypes.c_int,
                                  c_bool=local.ctypes.c_bool,
                                  c_uint=local.ctypes.c_uint,
                                  c_size_t=local.ctypes.c_size_t,
                                  c_ssize_t=local.ctypes.c_ssize_t)
        with patch.object(local.os, "name", "nt"), patch.object(local.sys, "frozen", True, create=True), patch.object(
            local, "ctypes", windows
        ):
            with local.progression_migration():
                fenetre.EnableWindow.assert_called_once_with(5678, False)
                self.assertFalse(fermeture.is_set())
            fenetre.PostMessageW.assert_called_once_with(1234, 0x10, 0, 0)
            self.assertTrue(fermeture.is_set())

    def test_demarrage_graphique_ecrit_le_journal_sans_alerte(self):
        with tempfile.TemporaryDirectory() as temporaire:
            with patch.object(local, "paquet_par_defaut", return_value=Path(temporaire) / "paquet-autonome"), patch.object(
                local, "main", side_effect=lambda: print("démarrage fictif")
            ), patch.object(local, "afficher_erreur_windows") as alerte, patch.object(
                sys, "argv", ["PetitsPas.exe"]
            ):
                local.demarrer_windows()
            journal = Path(temporaire) / "logs" / "dernier-demarrage.log"
            self.assertIn("démarrage fictif", journal.read_text(encoding="utf-8"))
            alerte.assert_not_called()

    def test_demarrage_graphique_journalise_les_erreurs_sans_console(self):
        with tempfile.TemporaryDirectory() as temporaire:
            paquet = Path(temporaire) / "paquet-autonome"
            with patch.object(local, "paquet_par_defaut", return_value=paquet), patch.object(
                local, "main", side_effect=RuntimeError("échec fictif")
            ), patch.object(local, "afficher_erreur_windows") as alerte, patch.object(
                sys, "argv", ["PetitsPas.exe"]
            ):
                with self.assertRaises(SystemExit) as sortie:
                    local.demarrer_windows()
            self.assertEqual(sortie.exception.code, 1)
            journal = Path(temporaire) / "logs" / "dernier-demarrage.log"
            self.assertIn("échec fictif", journal.read_text(encoding="utf-8"))
            alerte.assert_called_once()
            self.assertIn(str(journal), alerte.call_args.args[0])

    def test_verification_distribution_ne_bloque_pas_sur_une_alerte(self):
        with tempfile.TemporaryDirectory() as temporaire:
            with patch.object(local, "paquet_par_defaut", return_value=Path(temporaire) / "paquet-autonome"), patch.object(
                local, "main", side_effect=RuntimeError("échec de vérification")
            ), patch.object(local, "afficher_erreur_windows") as alerte, patch.object(
                sys, "argv", ["PetitsPas.exe", "--verifier-distribution"]
            ):
                with self.assertRaises(SystemExit):
                    local.demarrer_windows()
            alerte.assert_not_called()

    def test_spec_trouve_le_lanceur_depuis_la_racine_ou_scripts(self):
        racine = Path(__file__).resolve().parent.parent
        hooks = ModuleType("PyInstaller.utils.hooks")
        hooks.collect_data_files = lambda *args, **kwargs: []
        hooks.collect_submodules = lambda *args, **kwargs: []
        modules = {
            nom: ModuleType(nom)
            for nom in ("PyInstaller", "PyInstaller.utils")
        }
        modules[hooks.__name__] = hooks
        with tempfile.TemporaryDirectory() as temporaire:
            # Le .spec vérifie la présence des DLL avant d'appeler Analysis.
            # Le test fournit des fichiers fictifs pour rester indépendant de MSYS2.
            dlls = (
                "libgobject-2.0-0.dll", "libpango-1.0-0.dll",
                "libpangoft2-1.0-0.dll", "libharfbuzz-0.dll",
                "libharfbuzz-subset-0.dll", "libfontconfig-1.dll",
            )
            for nom in dlls:
                (Path(temporaire) / nom).touch()
            for emplacement in (racine, racine / "scripts"):
                with self.subTest(emplacement=emplacement), patch.dict(sys.modules, modules), patch.dict(
                    os.environ, {"PETITS_PAS_PANGO_BIN": temporaire}
                ):
                    appels = []
                    consoles = []

                    def analyser(scripts, **kwargs):
                        appels.extend(scripts)
                        self.assertIn("whitenoise.storage", kwargs["hiddenimports"])
                        self.assertIn("whitenoise.middleware", kwargs["hiddenimports"])
                        if os.name == "nt":
                            self.assertIn(
                                (str(Path(temporaire) / "libgobject-2.0-0.dll"), "."),
                                kwargs["binaries"],
                            )
                        return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

                    espace = {
                        "SPECPATH": str(emplacement),
                        "Analysis": analyser,
                        "PYZ": lambda *args: None,
                        "EXE": lambda *args, **kwargs: consoles.append(kwargs["console"]),
                        "COLLECT": lambda *args, **kwargs: None,
                    }
                    code = (racine / "scripts" / "PetitsPas.spec").read_text()
                    exec(compile(code, "PetitsPas.spec", "exec"), espace)
                    self.assertEqual(appels, [str(racine / "scripts" / "lancer-local.py")])
                    self.assertEqual(consoles, [os.name != "nt"])

    @unittest.skipIf(os.name == "nt", "WebKitGTK concerne Linux")
    def test_spec_embarque_typelib_webkit(self):
        racine = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporaire:
            typelib = Path(temporaire) / "WebKit2-4.1.typelib"
            typelib.write_bytes(b"typelib")
            hooks = ModuleType("PyInstaller.utils.hooks")
            hooks.collect_data_files = lambda *args, **kwargs: []
            hooks.collect_submodules = lambda *args, **kwargs: []
            modules = {nom: ModuleType(nom) for nom in ("PyInstaller", "PyInstaller.utils")}
            modules[hooks.__name__] = hooks

            def analyser(scripts, **kwargs):
                self.assertIn("gi.repository.WebKit2", kwargs["hiddenimports"])
                self.assertIn((str(typelib), "gi_typelibs"), kwargs["datas"])
                return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

            espace = {
                "SPECPATH": str(racine), "Analysis": analyser,
                "PYZ": lambda *args: None, "EXE": lambda *args, **kwargs: None,
                "COLLECT": lambda *args, **kwargs: None,
            }
            with patch.dict(sys.modules, modules), patch.dict(os.environ, {"GI_TYPELIB_PATH": temporaire}):
                code = (racine / "scripts" / "PetitsPas.spec").read_text()
                exec(compile(code, "PetitsPas.spec", "exec"), espace)

    def test_emplacement_windows_utilise_localappdata(self):
        environnement = SimpleNamespace(
            name="nt", environ={"LOCALAPPDATA": "C:/Users/test/AppData/Local"}
        )
        with patch.object(local, "os", environnement):
            self.assertEqual(
                local.paquet_par_defaut(),
                Path("C:/Users/test/AppData/Local/petits-pas/paquet-autonome"),
            )

    @unittest.skipIf(os.name == "nt", "Installateur Ubuntu")
    def test_installation_linux_conserve_les_donnees_et_la_version_precedente(self):
        racine = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            sources = dossier / "extraction" / "PetitsPas"
            sources.mkdir(parents=True)
            (sources / "_internal").mkdir()
            executable = sources / "PetitsPas"
            executable.write_bytes(b"premiere version")
            executable.chmod(0o755)
            script = sources / "installer-paquet-linux.sh"
            script.write_bytes((racine / "scripts" / script.name).read_bytes())
            gestion = sources / "gerer-versions-linux.sh"
            gestion.write_bytes((racine / "scripts" / gestion.name).read_bytes())
            donnees = dossier / "donnees"
            paquet = donnees / "petits-pas" / "paquet-autonome"
            paquet.mkdir(parents=True)
            (paquet / "carnet.sqlite3").write_bytes(b"base fictive")
            environnement = {**os.environ, "XDG_DATA_HOME": str(donnees)}

            def installer():
                subprocess.run(["bash", str(script)], check=True, env=environnement,
                               capture_output=True, text=True)

            installer()
            programmes = donnees / "petits-pas" / "programmes"
            versions = lambda: [p for p in programmes.iterdir() if p.is_dir()]
            self.assertEqual(len(versions()), 1)
            installer()
            self.assertEqual(len(versions()), 1)
            executable.write_bytes(b"seconde version")
            installer()
            self.assertEqual(len(versions()), 2)
            self.assertEqual({(p / "PetitsPas").read_bytes() for p in versions()},
                             {b"premiere version", b"seconde version"})
            (sources / "_internal" / "style.css").write_bytes(b"nouveau style")
            installer()
            self.assertEqual(len(versions()), 3)
            actif = (programmes / "actuelle").read_text().strip()
            avant = (programmes / "precedente").read_text().strip()
            self.assertNotEqual(actif, avant)
            subprocess.run(["bash", str(gestion), "--revenir"], check=True,
                           env=environnement, capture_output=True)
            self.assertEqual((programmes / "actuelle").read_text().strip(), avant)
            self.assertIn(avant, (donnees / "applications" / "petits-pas.desktop").read_text())
            subprocess.run(["bash", str(gestion), "--nettoyer"], check=True,
                           env=environnement, capture_output=True)
            self.assertEqual(len(versions()), 2)
            self.assertEqual((paquet / "carnet.sqlite3").read_bytes(), b"base fictive")
            lanceur = (donnees / "applications" / "petits-pas.desktop").read_text()
            self.assertIn("PetitsPas", lanceur)
            self.assertIn("Exec=", lanceur)

    def test_paquet_absent_apres_interruption_ne_devient_pas_un_paquet_vide(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            paquet = racine / "paquet"
            ancien = racine / ".paquet-avant-restauration-20260925-100000-abcd1234"
            ancien.mkdir()
            with patch.object(sys, "argv", ["lancer-local.py", "--paquet", str(paquet)]):
                with patch.dict("os.environ", {"DATABASE_URL": "", "CARNET_S3_BUCKET": "", "CARNET_ENVIRONNEMENT_EPHEMERE": ""}):
                    with self.assertRaisesRegex(SystemExit, "restauration a peut-être été interrompue"):
                        local.main()
            self.assertFalse(paquet.exists())

    def test_limites_et_migrations_inconnues_avant_import(self):
        with tempfile.TemporaryDirectory() as temporaire:
            parent = Path(temporaire)
            paquet = parent / "paquet"; paquet.mkdir()
            (paquet / "media").mkdir()
            (paquet / "secret-key").write_text("cle fictive")
            with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as db, db:
                db.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
                db.execute("INSERT INTO django_migrations VALUES ('suivi', '0001_fictive')")
            archive = parent / "copie.zip"
            creer_sauvegarde(paquet, archive)
            for options, message in [
                ({"taille_max": 10}, "taille autorisée"),
                ({"fichiers_max": 2}, "trop volumineuse"),
                ({"migrations_connues": set()}, "version plus récente"),
            ]:
                with self.assertRaisesRegex(ValueError, message):
                    preparer_restauration(archive, parent, **options)
                self.assertFalse(list(parent.glob(".restauration-*")))
                self.assertTrue((paquet / "carnet.sqlite3").exists())
            preparation = preparer_restauration(
                archive, parent, migrations_connues={("suivi", "0001_fictive")}
            )
            self.assertTrue(preparation.etape.is_dir())

    def test_sauvegarde_et_restauration_complete(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            paquet = racine / "paquet"
            paquet.mkdir()
            (paquet / "media").mkdir()
            (paquet / "media" / "photo.jpg").write_bytes(b"photo originale")
            (paquet / "secret-key").write_text("cle originale", encoding="utf-8")
            with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as connexion, connexion:
                connexion.execute("CREATE TABLE django_migrations (app TEXT)")
                connexion.execute("INSERT INTO django_migrations VALUES ('suivi')")
            archive = racine / "copie.zip"
            creer_sauvegarde(paquet, archive)
            (paquet / "media" / "photo.jpg").write_bytes(b"photo modifiee")
            etape = preparer_restauration(archive, racine)
            self.assertIsNotNone(etape.date_sauvegarde)
            self.assertEqual(etape.nombre_medias, 1)
            ancien = appliquer_restauration(paquet, etape)
            self.assertEqual(ancien, etape.ancien)
            self.assertEqual(lire_resultat(paquet)["ancien"], str(ancien))
            self.assertEqual(lire_resultat(paquet)["date_sauvegarde"], etape.date_sauvegarde)
            self.assertEqual((paquet / "media" / "photo.jpg").read_bytes(), b"photo originale")
            self.assertEqual((ancien / "media" / "photo.jpg").read_bytes(), b"photo modifiee")
            self.assertEqual((paquet / "secret-key").read_text(), "cle originale")
            with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as connexion:
                self.assertEqual(
                    connexion.execute("SELECT app FROM django_migrations").fetchone(),
                    ("suivi",),
                )

    def test_confirmation_et_annulation_conservent_le_paquet(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            paquet = racine / "paquet"
            paquet.mkdir()
            (paquet / "secret-key").write_text("cle")
            with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as connexion, connexion:
                connexion.execute("CREATE TABLE django_migrations (app TEXT)")
            archive = racine / "copie.zip"
            creer_sauvegarde(paquet, archive)
            preparation = preparer_restauration(archive, racine, paquet.name)
            retenir_preparation(preparation)
            self.assertEqual(preparation_en_attente(), preparation)
            self.assertTrue((paquet / "carnet.sqlite3").exists())
            annuler_preparation()
            self.assertIsNone(preparation_en_attente())
            self.assertFalse(preparation.etape.exists())
            preparation = preparer_restauration(archive, racine, paquet.name)
            retenir_preparation(preparation)
            import suivi.paquet_local as module
            try:
                self.assertEqual(confirmer_restauration(), preparation)
                self.assertIsNone(preparation_en_attente())
                self.assertTrue((paquet / "carnet.sqlite3").exists())
            finally:
                module._attente = None
                if preparation.etape.exists():
                    import shutil
                    shutil.rmtree(preparation.etape)

    def test_archive_invalide_ne_modifie_pas_le_paquet(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            archive = BytesIO()
            with ZipFile(archive, "w") as zip_fichier:
                zip_fichier.writestr("../photo.jpg", b"malveillant")
            archive.seek(0)
            with self.assertRaises(ValueError):
                preparer_restauration(archive, racine)
            self.assertFalse((racine / "photo.jpg").exists())

    def test_sauvegarde_modifiee_est_refusee(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            paquet = racine / "paquet"
            paquet.mkdir()
            (paquet / "media").mkdir()
            (paquet / "media" / "photo.jpg").write_bytes(b"photo")
            (paquet / "secret-key").write_text("cle", encoding="utf-8")
            with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as connexion, connexion:
                connexion.execute("CREATE TABLE django_migrations (app TEXT)")
            original = racine / "original.zip"
            creer_sauvegarde(paquet, original)
            modifie = racine / "modifie.zip"
            with ZipFile(original) as avant, ZipFile(modifie, "w") as apres:
                for nom in avant.namelist():
                    contenu = b"photo modifiee" if nom == "media/photo.jpg" else avant.read(nom)
                    apres.writestr(nom, contenu)
            with self.assertRaisesRegex(ValueError, "altéré"):
                preparer_restauration(modifie, racine)
            self.assertEqual((paquet / "media" / "photo.jpg").read_bytes(), b"photo")

    def test_transfert_conserve_donnees_et_refuse_ecrasement(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            source = racine / "ancien"
            source.mkdir()
            (source / "media").mkdir()
            (source / "media" / "photo.jpg").write_bytes(b"photo-test")
            (source / "secret-key").write_text("secret-test", encoding="utf-8")
            with closing(sqlite3.connect(source / "carnet.sqlite3")) as connexion, connexion:
                connexion.execute("CREATE TABLE test (valeur TEXT)")
                connexion.execute("INSERT INTO test VALUES ('conserve')")
            destination = racine / "nouveau" / "paquet-autonome"
            local.copier_paquet(source, destination)
            self.assertEqual((destination / "media" / "photo.jpg").read_bytes(), b"photo-test")
            self.assertEqual((destination / "secret-key").read_text(), "secret-test")
            with closing(sqlite3.connect(destination / "carnet.sqlite3")) as connexion:
                self.assertEqual(connexion.execute("SELECT valeur FROM test").fetchone(), ("conserve",))
            self.assertTrue((source / "carnet.sqlite3").exists())
            with self.assertRaises(SystemExit):
                local.copier_paquet(source, destination)

    def test_configuration_utilise_la_cle_du_paquet(self):
        with tempfile.TemporaryDirectory() as temporaire:
            paquet = Path(temporaire)
            with patch.dict("os.environ", {}, clear=True):
                local.configurer_environnement(paquet, "cle-conservee")
                self.assertEqual(local.os.environ["CARNET_SECRET_KEY"], "cle-conservee")
                self.assertEqual(
                    local.os.environ["CARNET_SQLITE_PATH"],
                    str(paquet / "carnet.sqlite3"),
                )

    def test_repertoire_xdg(self):
        environnement = SimpleNamespace(
            name="posix", environ={"XDG_DATA_HOME": "/tmp/donnees-test"}
        )
        with patch.object(local, "os", environnement):
            self.assertEqual(
                local.paquet_par_defaut(),
                Path("/tmp/donnees-test/petits-pas/paquet-autonome"),
            )

    def test_deux_instances_ne_peuvent_ouvrir_le_meme_paquet(self):
        with tempfile.TemporaryDirectory() as temporaire:
            paquet = Path(temporaire)
            with local.verrouiller(paquet):
                with self.assertRaises(SystemExit):
                    with local.verrouiller(paquet):
                        pass


if __name__ == "__main__":
    unittest.main()
