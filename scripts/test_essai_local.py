"""Isolation des essais et refus de remplacer un paquet existant."""
import importlib.util
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from suivi.essai_local import installer_ecole_fictive
from suivi.paquet_local import creer_sauvegarde

spec = importlib.util.spec_from_file_location("lanceur_essai", Path(__file__).with_name("lancer-local.py"))
local = importlib.util.module_from_spec(spec); spec.loader.exec_module(local)


class EssaiTests(unittest.TestCase):
    def test_chemin_essai_ignore_le_paquet_personnalise(self):
        with tempfile.TemporaryDirectory() as dossier:
            root = Path(dossier); defaut = root / "application/paquet-autonome"
            habituel = root / "ecole-personnelle"
            self.assertEqual(local.choisir_paquet(habituel, defaut), habituel)
            self.assertEqual(local.choisir_paquet(habituel, defaut, True), root / "application/essai-fictif")
            self.assertFalse(habituel.exists())

    def test_lien_symbolique_ou_chemin_identique_refuse(self):
        with tempfile.TemporaryDirectory() as dossier:
            root = Path(dossier); defaut = root / "paquet-autonome"; essai = root / "essai-fictif"
            with self.assertRaises(ValueError): local.choisir_paquet(essai, defaut, True)
            try:
                essai.symlink_to(defaut, target_is_directory=True)
            except OSError:
                self.skipTest("Création de liens symboliques indisponible sur ce système")
            with self.assertRaises(ValueError): local.choisir_paquet(defaut, defaut, True)

    def test_zip_installe_seulement_dans_un_dossier_vierge(self):
        with tempfile.TemporaryDirectory() as dossier:
            root = Path(dossier); paquet = root / "source"; paquet.mkdir(); (paquet / "media").mkdir()
            (paquet / "secret-key").write_text("cle-fictive")
            with sqlite3.connect(paquet / "carnet.sqlite3") as db:
                db.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
                db.execute("CREATE TABLE preuve (nom TEXT)"); db.execute("INSERT INTO preuve VALUES ('fictif')")
            zip = BytesIO(); creer_sauvegarde(paquet, zip)
            destination = root / "essai"; installer_ecole_fictive(zip.getvalue(), destination)
            original = (destination / "carnet.sqlite3").read_bytes()
            with self.assertRaises(ValueError): installer_ecole_fictive(zip.getvalue(), destination)
            self.assertEqual((destination / "carnet.sqlite3").read_bytes(), original)
            (root / "occupe").mkdir(); (root / "occupe/conserver").write_text("intact")
            with self.assertRaises(ValueError): installer_ecole_fictive(zip.getvalue(), root / "occupe")
            self.assertEqual((root / "occupe/conserver").read_text(), "intact")

    def test_zip_invalide_ne_cree_pas_de_base(self):
        with tempfile.TemporaryDirectory() as dossier:
            destination = Path(dossier) / "essai"
            with self.assertRaises(Exception): installer_ecole_fictive(b"invalide", destination)
            self.assertFalse(destination.exists())
