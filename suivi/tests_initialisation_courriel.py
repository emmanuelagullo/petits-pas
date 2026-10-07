from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.contrib.auth.tokens import default_token_generator

from comptes.models import ResponsabiliteEcole
from suivi.models import Ecole


@override_settings(EMAIL_DISPONIBLE=True,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OuvertureCourrielTests(TestCase):
    def ouvrir(self, **options):
        valeurs = dict(ecole='École test', commune='Fictive', prenom='Camille',
                       nom='Martin', utilisateur='camille', email='camille@example.test',
                       url='https://ecole.example.test', stdout=StringIO())
        valeurs.update(options)
        call_command('initialiser_ecole_serveur', **valeurs)
        return valeurs['stdout'].getvalue()

    def test_courriel_et_choix_personnel_du_mot_de_passe(self):
        sortie = self.ouvrir()
        user = get_user_model().objects.get()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(ResponsabiliteEcole.objects.get().type, ResponsabiliteEcole.DIRECTION)
        self.assertTrue(user.has_usable_password())
        self.assertIn(user.username, mail.outbox[0].body)
        self.assertIn(user.email, mail.outbox[0].body)
        self.assertIn("ne donnent pas automatiquement accès", mail.outbox[0].body)
        self.assertIn("Activer la classe", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")
        lien = next(l for l in mail.outbox[0].body.splitlines() if l.startswith('https://'))
        self.assertNotIn(lien, sortie)
        token = lien.rstrip('/').split('/')[-1]
        self.assertTrue(default_token_generator.check_token(user, token))
        # Le vrai écran Django doit permettre le choix, puis rendre le lien inutilisable.
        chemin = lien.removeprefix('https://ecole.example.test')
        reponse = self.client.get(chemin)
        self.assertEqual(reponse.status_code, 302)
        reponse = self.client.post(reponse.url, {
            'new_password1': 'Personnel!2026UneLonguePhrase',
            'new_password2': 'Personnel!2026UneLonguePhrase',
        })
        self.assertEqual(reponse.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Personnel!2026UneLonguePhrase'))
        self.assertFalse(default_token_generator.check_token(user, token))

    def test_ajout_explicitement_autorise_et_doublon_refuse(self):
        self.ouvrir()
        with self.assertRaises(CommandError):
            self.ouvrir(ecole='Autre école', utilisateur='autre', email='autre@example.test')
        self.ouvrir(ecole='Autre école', utilisateur='autre', email='autre@example.test', ajouter_ecole=True)
        with self.assertRaises(CommandError):
            self.ouvrir(ajouter_ecole=True)
        self.assertEqual(Ecole.objects.count(), 2)

    def test_courrier_desactive_et_url_invalide_refusent_avant_creation(self):
        with override_settings(EMAIL_DISPONIBLE=False), self.assertRaises(CommandError):
            self.ouvrir()
        with self.assertRaises(CommandError):
            self.ouvrir(url='http://ecole.example.test')
        with self.assertRaises(CommandError):
            self.ouvrir(email=" ")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"), self.assertRaises(CommandError):
            self.ouvrir()
        self.assertFalse(Ecole.objects.exists())

    @patch('suivi.courriels_comptes.EmailMultiAlternatives.send', side_effect=OSError)
    def test_echec_envoi_preserve_compte_pour_recuperation(self, _send):
        with self.assertRaisesMessage(CommandError, 'Ne pas recréer'):
            self.ouvrir()
        self.assertEqual(Ecole.objects.count(), 1)
        self.assertEqual(get_user_model().objects.get().email, 'camille@example.test')
