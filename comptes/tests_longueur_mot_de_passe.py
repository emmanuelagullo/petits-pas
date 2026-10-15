"""Plafond de longueur des mots de passe."""
from unittest import mock

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .validators import LONGUEUR_MAX_MOT_DE_PASSE


class LongueurMotDePasse(TestCase):
    def setUp(self):
        self.utilisateur = get_user_model().objects.create_user("lea")
        self.requete = RequestFactory().post("/connexion/")

    def test_la_limite_exacte_est_acceptee(self):
        mot_de_passe = "a1" * (LONGUEUR_MAX_MOT_DE_PASSE // 2)
        self.utilisateur.set_password(mot_de_passe)
        self.utilisateur.save()
        self.assertEqual(authenticate(self.requete, username="lea", password=mot_de_passe), self.utilisateur)

    def test_au_dela_de_la_limite_l_authentification_echoue_sans_hacher(self):
        long = "a" * (LONGUEUR_MAX_MOT_DE_PASSE + 1)
        self.utilisateur.set_password("x" * 20)
        self.utilisateur.save()
        with mock.patch.object(get_user_model(), "check_password") as hachage:
            self.assertIsNone(authenticate(self.requete, username="lea", password=long))
        hachage.assert_not_called()

    def test_un_mot_de_passe_trop_long_est_refuse_a_la_creation(self):
        with self.assertRaises(ValidationError) as erreur:
            validate_password("aB3$" * 300)
        self.assertIn("trop long", " ".join(erreur.exception.messages))

    def test_la_connexion_repond_comme_pour_un_mot_de_passe_faux(self):
        reponse = self.client.post(reverse("connexion"), {
            "nom_utilisateur": "lea", "mot_de_passe": "a" * 2_000_000})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Nom d&#x27;utilisateur ou mot de passe incorrect.")

    def test_une_session_ouverte_avec_le_backend_standard_reste_valide(self):
        """Le plafond ne doit pas changer le chemin du backend mémorisé en session."""
        self.client.force_login(
            self.utilisateur, backend="django.contrib.auth.backends.ModelBackend")
        reponse = self.client.get(reverse("accueil"))
        self.assertNotEqual(reponse.get("Location"), reverse("connexion"))
        self.assertIn("_auth_user_id", self.client.session)
