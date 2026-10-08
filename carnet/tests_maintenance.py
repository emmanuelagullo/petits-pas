import json
import tempfile
import time
from pathlib import Path
from django.test import SimpleTestCase, override_settings

class AnnonceTests(SimpleTestCase):
    @override_settings(MAINTENANCE_ANNONCE="")
    def test_absence(self):
        r = self.client.get("/maintenance-annonce/")
        self.assertEqual(r.json(), {"debut": None})
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertEqual(self.client.post("/maintenance-annonce/").status_code, 405)

    def test_active_expiree_invalide_et_lien(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "annonce.json"
            with override_settings(MAINTENANCE_ANNONCE=str(p)):
                maintenant = time.time()
                p.write_text(json.dumps({"debut": maintenant+60, "expiration": maintenant+120}))
                self.assertEqual(self.client.get("/maintenance-annonce/").json()["debut"], maintenant+60)
                for contenu in ('{}', 'secret', json.dumps({"debut": 1, "expiration": 2}), '{"debut":NaN,"expiration":NaN}'):
                    p.write_text(contenu)
                    self.assertEqual(self.client.get("/maintenance-annonce/").json(), {"debut": None})
                cible = Path(d)/"cible"; p.rename(cible); p.symlink_to(cible)
                self.assertEqual(self.client.get("/maintenance-annonce/").json(), {"debut": None})

    def test_annonce_ne_declenche_pas_le_controle_double_facteur(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from suivi.acces_double_facteur import DoubleFacteurMiddleware
        request = SimpleNamespace(resolver_match=SimpleNamespace(url_name='maintenance_annonce'))
        self.assertIsNone(DoubleFacteurMiddleware(Mock()).process_view(request, Mock(), (), {}))
