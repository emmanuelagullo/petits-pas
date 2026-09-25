"""Contrôles des opérations sur les données autonomes, sans Django ni GTK."""

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "lancer_local", Path(__file__).with_name("lancer-local.py")
)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class PaquetLocalTests(unittest.TestCase):
    def test_transfert_conserve_donnees_et_refuse_ecrasement(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            source = racine / "ancien"
            source.mkdir()
            (source / "media").mkdir()
            (source / "media" / "photo.jpg").write_bytes(b"photo-test")
            (source / "secret-key").write_text("secret-test", encoding="utf-8")
            with sqlite3.connect(source / "carnet.sqlite3") as connexion:
                connexion.execute("CREATE TABLE test (valeur TEXT)")
                connexion.execute("INSERT INTO test VALUES ('conserve')")
            destination = racine / "nouveau" / "paquet-autonome"
            local.copier_paquet(source, destination)
            self.assertEqual((destination / "media" / "photo.jpg").read_bytes(), b"photo-test")
            self.assertEqual((destination / "secret-key").read_text(), "secret-test")
            with sqlite3.connect(destination / "carnet.sqlite3") as connexion:
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
        with patch.dict("os.environ", {"XDG_DATA_HOME": "/tmp/donnees-test"}):
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
