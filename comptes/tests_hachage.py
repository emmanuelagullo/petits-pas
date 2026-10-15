"""Conserver un vrai parcours d'authentification avec le hachage ordinaire."""

from django.conf.global_settings import PASSWORD_HASHERS
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import identify_hasher
from django.test import TestCase, override_settings


@override_settings(PASSWORD_HASHERS=PASSWORD_HASHERS)
class HachageOrdinaire(TestCase):
    def test_authentification_et_changement_de_mot_de_passe(self):
        utilisateur = get_user_model().objects.create_user(
            username="hachage-fictif", password="Premier!Fictif2026"
        )
        self.assertEqual(identify_hasher(utilisateur.password).algorithm, "pbkdf2_sha256")
        backend = ModelBackend()
        self.assertIsNotNone(backend.authenticate(
            None, username=utilisateur.username, password="Premier!Fictif2026"
        ))
        self.assertIsNone(backend.authenticate(
            None, username=utilisateur.username, password="Incorrect!Fictif2026"
        ))
        utilisateur.set_password("Second!Fictif2026")
        utilisateur.save(update_fields=["password"])
        self.assertIsNone(backend.authenticate(
            None, username=utilisateur.username, password="Premier!Fictif2026"
        ))
        self.assertIsNotNone(backend.authenticate(
            None, username=utilisateur.username, password="Second!Fictif2026"
        ))
