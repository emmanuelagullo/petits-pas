"""Calcul TOTP et analyse de pages du scénario de déploiement du second facteur."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "exercer_double_facteur", Path(__file__).with_name("exercer-double-facteur.py"))
scenario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenario)

# Secret de test de la RFC 6238 (« 12345678901234567890 ») en base32.
CLE_RFC = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class CodeTotp(unittest.TestCase):
    def test_vecteurs_de_la_rfc_6238(self):
        # Valeurs SHA-1 de l'annexe B, tronquées aux six derniers chiffres.
        for instant, attendu in {
            59: "287082", 1111111109: "081804", 1111111111: "050471",
            1234567890: "005924", 2000000000: "279037", 20000000000: "353130",
        }.items():
            with self.subTest(instant=instant):
                self.assertEqual(scenario.code_totp(CLE_RFC, instant), attendu)

    def test_un_pas_de_trente_secondes(self):
        self.assertEqual(scenario.code_totp(CLE_RFC, 30), scenario.code_totp(CLE_RFC, 59))
        self.assertNotEqual(scenario.code_totp(CLE_RFC, 29), scenario.code_totp(CLE_RFC, 30))

    def test_cle_sans_remplissage_base32(self):
        self.assertEqual(scenario.code_totp(CLE_RFC.rstrip("="), 59), "287082")


class AnalyseDesPages(unittest.TestCase):
    def test_jeton_csrf(self):
        page = '<input type="hidden" name="csrfmiddlewaretoken" value="abc123XYZ">'
        self.assertEqual(scenario.JETON_CSRF.search(page).group(1), "abc123XYZ")

    def test_cle_saisie_a_la_main(self):
        page = "<p>Saisissez cette clé : <code>ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567</code></p>"
        self.assertEqual(
            scenario.CLE_SAISIE.search(page).group(1).replace(" ", ""),
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

    def test_codes_de_secours(self):
        page = "<li><code>ABCD-EFGH-JKLM-NPQR</code></li><li><code>2345-6789-ABCD-EFGH</code></li>"
        self.assertEqual(
            scenario.CODES_SECOURS.findall(page), ["ABCD-EFGH-JKLM-NPQR", "2345-6789-ABCD-EFGH"])

    def test_les_expressions_ne_confondent_pas_cle_et_codes(self):
        self.assertIsNone(scenario.CLE_SAISIE.search("<code>ABCD-EFGH-JKLM-NPQR</code>"))
        self.assertIsNone(scenario.CODES_SECOURS.search("<code>ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567</code>"))

    def test_une_condition_fausse_arrete_le_scenario(self):
        with self.assertRaises(SystemExit):
            scenario.verifier(False, "doit échouer")


if __name__ == "__main__":
    unittest.main()
