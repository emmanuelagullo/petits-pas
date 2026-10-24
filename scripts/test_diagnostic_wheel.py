"""Contrôler les erreurs réseau et l’intégrité sans requête extérieure."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
import urllib.error

spec = importlib.util.spec_from_file_location(
    "diagnostic_wheel", Path(__file__).with_name("diagnostiquer-wheel.py"))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class DiagnosticWheelTests(unittest.TestCase):
    def executer(self, response=None, erreur=None, empreinte=None):
        sortie = io.StringIO()
        opener = Mock()
        opener.open.side_effect = erreur
        opener.open.return_value = response
        with patch.object(diagnostic.urllib.request, "build_opener", return_value=opener), contextlib.redirect_stdout(sortie):
            resultat = diagnostic.sonder("wheel", "https://github.com/wheel", empreinte)
        return resultat, sortie.getvalue()

    def test_empreinte_du_contenu_reel(self):
        def response():
            r = io.BytesIO(b"wheel")
            r.code, r.url, r.headers = 200, "https://assets.example/wheel?secret=cache", {}
            return r
        ok, texte = self.executer(response(), empreinte=hashlib.sha256(b"wheel").hexdigest())
        self.assertTrue(ok)
        self.assertNotIn("secret", texte)
        self.assertFalse(self.executer(response(), empreinte="0" * 64)[0])

    def test_502_garde_les_indices_sans_corps_ni_url_signee(self):
        erreur = urllib.error.HTTPError("https://assets.example/?secret=jeton", 502, "Bad Gateway",
            {"Server": "proxy-test", "Via": "cache-test", "Set-Cookie": "secret=jeton"}, io.BytesIO(b"secret=jeton"))
        ok, texte = self.executer(erreur=erreur)
        self.assertFalse(ok)
        self.assertIn("HTTP 502", texte)
        self.assertIn("Via: cache-test", texte)
        self.assertNotIn("secret", texte)

    def test_erreur_transport_ne_divulgue_pas_son_message(self):
        ok, texte = self.executer(erreur=urllib.error.URLError("proxy:mot-de-passe"))
        self.assertFalse(ok)
        self.assertIn("URLError", texte)
        self.assertNotIn("mot-de-passe", texte)
