from django.test import Client, TestCase
from django.urls import reverse


class RefusCsrfTests(TestCase):
    def test_reprise_accessible_sans_session_et_requete_pas_rejouee(self):
        client = Client(enforce_csrf_checks=True)
        reponse = client.post(reverse("connexion"), {"csrfmiddlewaretoken": "invalide"},
                              HTTP_HX_REQUEST="true")
        self.assertContains(reponse, "Cette demande n’a pas été enregistrée", status_code=403)
        self.assertContains(reponse, f'href="{reverse("accueil")}"', status_code=403)
        self.assertEqual(reponse["X-Petits-Pas-Refus"], "csrf")
        self.assertEqual(reponse["Cache-Control"], "no-store")
        self.assertNotIn("_auth_user_id", client.session)
