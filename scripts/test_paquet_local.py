"""Contrôles des opérations sur les données autonomes, sans Django ni GTK."""

import importlib.util
import os
from contextlib import closing
import sqlite3
import sys
from types import SimpleNamespace
from types import ModuleType
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from suivi.paquet_local import (
    annuler_preparation,
    appliquer_restauration,
    confirmer_restauration,
    creer_sauvegarde,
    lire_resultat,
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
        for emplacement in (racine, racine / "scripts"):
            with self.subTest(emplacement=emplacement), patch.dict(sys.modules, modules):
                appels = []

                def analyser(scripts, **kwargs):
                    appels.extend(scripts)
                    self.assertIn("whitenoise.storage", kwargs["hiddenimports"])
                    self.assertIn("whitenoise.middleware", kwargs["hiddenimports"])
                    return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

                espace = {
                    "SPECPATH": str(emplacement),
                    "Analysis": analyser,
                    "PYZ": lambda *args: None,
                    "EXE": lambda *args, **kwargs: None,
                    "COLLECT": lambda *args, **kwargs: None,
                }
                code = (racine / "scripts" / "PetitsPas.spec").read_text()
                exec(compile(code, "PetitsPas.spec", "exec"), espace)
                self.assertEqual(appels, [str(racine / "scripts" / "lancer-local.py")])

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
