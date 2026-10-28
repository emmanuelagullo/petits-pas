import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

specification = importlib.util.spec_from_file_location("mesure", Path(__file__).with_name("mesurer-bundle-macos.py"))
mesure = importlib.util.module_from_spec(specification)
specification.loader.exec_module(mesure)

EN_TETE = "x:\n"
SYSTEME = "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n\t@loader_path/libfoo.dylib (compatibility version 1.0.0)\n"
EXTERNE = "\t/opt/homebrew/opt/glib/lib/libgobject-2.0.0.dylib (compatibility version 1.0.0)\n"


def commandes(versions, externes=()):
    """Faux otool : version minimale par nom de fichier, dépendances externes pour certains."""
    def executer(commande, **options):
        fichier = Path(commande[2]).name
        if commande[1] == "-L":
            return SimpleNamespace(stdout=EN_TETE + SYSTEME + (EXTERNE if fichier in externes else ""))
        return SimpleNamespace(stdout=f"Load command 9\n      cmd LC_BUILD_VERSION\n  cmdsize 32\nplatform 1\n    minos {versions[fichier]}\n      sdk 15.2\n")
    return executer


class MesureBundleMacosTests(unittest.TestCase):
    def application(self, temporaire, noms):
        racine = Path(temporaire) / "PetitsPas.app"
        racine.mkdir()
        for nom in noms:
            (racine / nom).write_bytes(b"\xcf\xfa\xed\xfe" + b"0" * 8)
        (racine / "Info.plist").write_text("pas un binaire")
        return racine

    def test_bundle_conforme(self):
        with tempfile.TemporaryDirectory() as t:
            application = self.application(t, ["PetitsPas", "libthai.0.dylib", "libpango.dylib"])
            code, lignes = mesure.mesurer(application, (15,),
                commandes({"PetitsPas": "11.0", "libthai.0.dylib": "15.0", "libpango.dylib": "14.0"}))
            self.assertEqual(code, 0)
            self.assertIn("3 fichiers Mach-O mesurés.", lignes)
            self.assertTrue(any("15.0, imposée par libthai.0.dylib" in ligne for ligne in lignes))

    def test_version_exigee_superieure_a_celle_annoncee(self):
        with tempfile.TemporaryDirectory() as t:
            application = self.application(t, ["PetitsPas", "libthai.0.dylib"])
            code, lignes = mesure.mesurer(application, (15,), commandes({"PetitsPas": "11.0", "libthai.0.dylib": "16.0"}))
            self.assertEqual(code, 1)
            self.assertTrue(any("exige macOS 16.0" in ligne for ligne in lignes))

    def test_dependance_hors_du_systeme_et_du_bundle(self):
        with tempfile.TemporaryDirectory() as t:
            application = self.application(t, ["PetitsPas", "libpango.dylib"])
            code, lignes = mesure.mesurer(application, (15,),
                commandes({"PetitsPas": "11.0", "libpango.dylib": "14.0"}, externes={"libpango.dylib"}))
            self.assertEqual(code, 1)
            self.assertTrue(any("libpango.dylib" in ligne and "/opt/homebrew" in ligne for ligne in lignes))

    def test_versions_comparees_sans_piege_de_longueur(self):
        self.assertEqual(mesure.normalisee((15,)), mesure.normalisee((15, 0)))
        self.assertLess(mesure.normalisee((15,)), mesure.normalisee((15, 1)))
        with tempfile.TemporaryDirectory() as t:
            application = self.application(t, ["PetitsPas"])
            self.assertEqual(mesure.mesurer(application, (15,), commandes({"PetitsPas": "15.0"}))[0], 0)
            self.assertEqual(mesure.mesurer(application, (15,), commandes({"PetitsPas": "15.1"}))[0], 1)
            self.assertEqual(mesure.mesurer(application, (15, 1), commandes({"PetitsPas": "15.1"}))[0], 0)

    def test_rien_a_mesurer(self):
        with tempfile.TemporaryDirectory() as t:
            code, lignes = mesure.mesurer(Path(t), (15,), commandes({}))
            self.assertEqual(code, 2)

    def test_lecture_des_versions_minimales(self):
        ancien = "Load command 8\n      cmd LC_VERSION_MIN_MACOSX\n  cmdsize 16\n  version 10.13\n      sdk 10.15\n"
        self.assertEqual(mesure.version_minimale("x", lambda *a, **k: SimpleNamespace(stdout=ancien)), (10, 13))
        self.assertEqual(mesure.version_minimale("x", lambda *a, **k: SimpleNamespace(stdout="")), (0,))
        self.assertEqual(mesure.texte_version((15, 0)), "15.0")
