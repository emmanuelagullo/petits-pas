from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from suivi import apercu_local
from suivi.models import Ecole


class ApercuLocalTests(TestCase):
    def tearDown(self):
        apercu_local.annuler()

    def test_aucun_parcours_sur_service_heberge(self):
        self.assertEqual(self.client.get(reverse("verifier_zip_local")).status_code, 404)

    @override_settings(MODE_LOCAL=True)
    def test_accessible_avant_initialisation_et_pas_de_creation_sur_zip_invalide(self):
        self.assertContains(self.client.get(reverse("verifier_zip_local")), "Vérifier un ZIP")
        archive = SimpleUploadedFile("fictif.zip", b"invalide")
        self.assertContains(self.client.post(reverse("verifier_zip_local"), {"action": "verifier", "archive": archive}), "Copie refusée")
        self.assertFalse(Ecole.objects.exists())
        self.assertIsNone(apercu_local.preparation())

    @override_settings(MODE_LOCAL=True)
    def test_upload_et_ouverture_exigent_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("verifier_zip_local"), {"action": "ouvrir"}).status_code, 403)

    @override_settings(MODE_LOCAL=True)
    def test_installation_directe_refuse_une_ecole_existante(self):
        ecole = Ecole.objects.create(nom="À conserver")
        self.assertContains(self.client.post(reverse("verifier_zip_local"), {"action": "installer_vide"}), "existe déjà")
        ecole.refresh_from_db(); self.assertEqual(ecole.nom, "À conserver")

    @override_settings(MODE_LOCAL=True)
    def test_installation_directe_refuse_un_compte_existant(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user(username="à-conserver")
        self.assertContains(self.client.post(reverse("verifier_zip_local"), {"action": "installer_vide"}), "existe déjà")

    @override_settings(MODE_LOCAL=True, ESPACE_APERCU=True)
    def test_bandeau_retour_et_aucune_copie_imbriquee(self):
        Ecole.objects.create(nom="Copie fictive")
        self.assertContains(self.client.get(reverse("connexion")), "Copie du ZIP à vérifier")
        self.assertContains(self.client.get(reverse("choisir_espace_local")), 'data-espace="habituel"')
        self.assertEqual(self.client.get(reverse("verifier_zip_local")).status_code, 404)
