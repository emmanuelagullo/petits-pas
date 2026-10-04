from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from io import StringIO
from suivi.models import Ecole


class EssaiLocalTests(TestCase):
    def test_aucun_selecteur_sur_le_service(self):
        self.assertEqual(self.client.get(reverse("choisir_espace_local")).status_code, 404)

    @override_settings(MODE_LOCAL=True, MODE_PWA=True)
    def test_navigateur_utilise_son_selecteur_de_coque(self):
        self.assertEqual(self.client.get(reverse("choisir_espace_local")).status_code, 404)

    @override_settings(MODE_LOCAL=True, ESPACE_ESSAI=True)
    def test_bandeau_et_retour_sur_connexion(self):
        Ecole.objects.create(nom="Fictif")
        self.assertContains(self.client.get(reverse("connexion")), "Espace d’essai")
        self.assertContains(self.client.get(reverse("choisir_espace_local")), 'data-espace="habituel"')

    @override_settings(MODE_LOCAL=True, ESPACE_ESSAI=False)
    def test_ecole_habituelle_peut_ouvrir_le_selecteur_sans_remplacement(self):
        ecole = Ecole.objects.create(nom="À conserver")
        self.assertContains(self.client.get(reverse("choisir_espace_local")), 'data-espace="essai"')
        ecole.refresh_from_db(); self.assertEqual(ecole.nom, "À conserver")

    def test_generation_commune_refuse_un_service_ordinaire(self):
        with self.assertRaises(CommandError): call_command("preparer_demonstration", stdout=StringIO())
        self.assertFalse(Ecole.objects.exists())

    @override_settings(ENVIRONNEMENT_EPHEMERE=True)
    def test_generation_commune_refuse_une_base_contenant_un_compte(self):
        get_user_model().objects.create_user(username="a-conserver")
        with self.assertRaises(CommandError): call_command("preparer_demonstration", stdout=StringIO())
        self.assertFalse(Ecole.objects.exists())
