"""Validation, connexion propre et retour au paquet habituel pour les copies ZIP."""
import importlib.util
from io import BytesIO
from contextlib import ExitStack, closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from suivi import apercu_local
from suivi.paquet_local import creer_sauvegarde

spec = importlib.util.spec_from_file_location("lanceur_apercu", Path(__file__).with_name("lancer-local.py"))
local = importlib.util.module_from_spec(spec); spec.loader.exec_module(local)


class ApercuTests(unittest.TestCase):
    def tearDown(self):
        apercu_local.annuler()

    def archive(self, root):
        paquet = root / "habituel"; paquet.mkdir(); (paquet / "media").mkdir()
        (paquet / "secret-key").write_text("cle-fictive")
        with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as db, db:
            db.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
            db.execute("INSERT INTO django_migrations VALUES ('suivi', 'fictive')")
            db.execute("CREATE TABLE django_session (session_key TEXT)")
            db.execute("INSERT INTO django_session VALUES ('session-originale')")
        archive = BytesIO(); creer_sauvegarde(paquet, archive); archive.seek(0)
        return paquet, archive

    def test_copie_validee_independante_sessions_effacees_retour_arguments(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as nettoyage:
            nettoyage.callback(apercu_local.annuler)
            root = Path(folder).resolve(); paquet, archive = self.archive(root)
            original = (paquet / "carnet.sqlite3").read_bytes()
            copie = apercu_local.preparer(archive, root, migrations_connues={('suivi', 'fictive')})
            with closing(sqlite3.connect(copie.etape / "carnet.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM django_session").fetchone()[0], 0)
            self.assertEqual((paquet / "carnet.sqlite3").read_bytes(), original)
            self.assertEqual(apercu_local.verifier_dossier(copie.etape, paquet, root / "essai"), copie.etape)
            arguments = ["PetitsPas", "--paquet", str(paquet), "--essai"]
            preview = local.arguments_espace(arguments, "apercu", copie.etape)
            self.assertEqual(local.arguments_espace(preview, "habituel"), arguments[:-1])
            self.assertEqual(local.arguments_espace(arguments[:-1] + ["--apercu=" + str(copie.etape)], "habituel"), arguments[:-1])
            with self.assertRaises(ValueError): apercu_local.verifier_dossier(copie.etape, copie.etape, root / "essai")
            apercu_local.annuler(); self.assertFalse(copie.etape.exists())

    def test_refus_migration_inconnue_et_zip_altere(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); paquet, archive = self.archive(root)
            with self.assertRaises(ValueError): apercu_local.preparer(archive, root, migrations_connues=set())
            self.assertIsNone(apercu_local.preparation())
            with self.assertRaises(Exception): apercu_local.preparer(BytesIO(b"zip-invalide"), root)
            self.assertEqual(list(root.iterdir()), [paquet])

    def test_ouverture_exige_copie_et_detachement_la_conserve(self):
        with self.assertRaises(ValueError): apercu_local.demander_ouverture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); _, archive = self.archive(root)
            copie = apercu_local.preparer(archive, root)
            apercu_local.demander_ouverture(); self.assertTrue(apercu_local.ouverture_demandee())
            self.assertEqual(apercu_local.detacher(), copie)
            apercu_local.annuler(); self.assertTrue(copie.etape.exists())
            self.assertEqual(apercu_local.derniere_copie(root, root / "habituel", root / "essai"), copie.etape)
            (copie.etape / apercu_local.MARQUEUR).write_text('[]')
            self.assertIsNone(apercu_local.derniere_copie(root, root / "habituel", root / "essai"))
