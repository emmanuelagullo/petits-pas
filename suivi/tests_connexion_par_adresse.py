"""Plafond d'échecs de connexion par adresse, tous identifiants confondus."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

MOT_DE_PASSE = "un-mot-de-passe-solide-1"


@override_settings(RATELIMIT_CONNEXION_IP="3/15m", ANTIBRUTEFORCE_ACTIF=True)
class ConnexionParAdresse(TestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user("lea", password=MOT_DE_PASSE)

    def echec(self, client, nom):
        return client.post(reverse("connexion"), {"nom_utilisateur": nom, "mot_de_passe": "faux"})

    def test_des_echecs_sur_des_identifiants_differents_finissent_par_bloquer_l_adresse(self):
        c = self.client_class(REMOTE_ADDR="10.9.0.1")
        for i in range(4):
            self.assertEqual(self.echec(c, f"inconnu{i}").status_code, 200)
        self.assertEqual(self.echec(c, "inconnu9").status_code, 429)

    def test_une_autre_adresse_n_est_pas_bloquee(self):
        c = self.client_class(REMOTE_ADDR="10.9.0.1")
        for i in range(5):
            self.echec(c, f"inconnu{i}")
        autre = self.client_class(REMOTE_ADDR="10.9.0.2")
        self.assertEqual(self.echec(autre, "inconnu").status_code, 200)

    def test_les_connexions_reussies_ne_comptent_pas(self):
        c = self.client_class(REMOTE_ADDR="10.9.0.3")
        for _ in range(8):
            c.post(reverse("connexion"), {"nom_utilisateur": "lea", "mot_de_passe": MOT_DE_PASSE})
            c.post(reverse("deconnexion"))
        reponse = c.post(reverse("connexion"), {"nom_utilisateur": "lea", "mot_de_passe": MOT_DE_PASSE})
        self.assertNotEqual(reponse.status_code, 429)

    @override_settings(ANTIBRUTEFORCE_ACTIF=False)
    def test_inactif_quand_l_antibruteforce_est_desactive(self):
        c = self.client_class(REMOTE_ADDR="10.9.0.4")
        for i in range(6):
            self.assertEqual(self.echec(c, f"x{i}").status_code, 200)
