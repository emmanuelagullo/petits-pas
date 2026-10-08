"""Courriels d'import fictifs : après commit, lien réel et reprise sans réimport."""
import io
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command, CommandError
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings

from comptes.models import Utilisateur, ResponsabiliteEcole
from . import models as m, tests_imports_ecole
from .accueil_import import envoyer_accueil_import
from .imports_ecole import verifier_zip


@override_settings(EMAIL_DISPONIBLE=True,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   ENVIRONNEMENT_EPHEMERE=False, ENVIRONNEMENT_ATELIER=False)
class AccueilImportTests(TransactionTestCase):
    def setUp(self):
        tests_imports_ecole.ImportEcoleTests.setUp(self)
        with verifier_zip(self.archive, self.root) as projection:
            self.somme = projection.rapport['sha256']

    def ouvrir(self, **options):
        valeurs = dict(travail=str(self.root), confirmer=True, sha256=self.somme,
            ecole='École importée fictive', direction='direction-import-mail', creer_direction=True,
            prenom='Camille', nom='Fictive', operateur=self.direction.username,
            email='camille@example.invalid', url='https://ecole.example.invalid', stdout=io.StringIO())
        valeurs.update(options)
        call_command('importer_ecole_zip', str(self.archive), **valeurs)
        return valeurs['stdout'].getvalue()

    def renvoyer(self, **options):
        valeurs = dict(ecole=m.Ecole.objects.get(nom='École importée fictive').pk,
            direction='direction-import-mail', operateur=self.direction.username,
            url='https://ecole.example.invalid', stdout=io.StringIO())
        valeurs.update(options)
        call_command('renvoyer_accueil_import', **valeurs)
        return valeurs['stdout'].getvalue()

    def test_envoi_apres_commit_et_choix_reel_du_mot_de_passe(self):
        from .courriels_comptes import EmailMultiAlternatives
        envoyer = EmailMultiAlternatives.send
        def apres_commit(message, **options):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(m.Ecole.objects.filter(nom='École importée fictive').exists())
            return envoyer(message, **options)
        with patch('suivi.management.commands.importer_ecole_zip.getpass', side_effect=AssertionError('aucun secret demandé')), \
                patch('suivi.courriels_comptes.EmailMultiAlternatives.send', new=apres_commit):
            sortie = self.ouvrir()
        compte = Utilisateur.objects.get(username='direction-import-mail')
        self.assertEqual(compte.email, 'camille@example.invalid')
        self.assertTrue(compte.has_usable_password())
        self.assertFalse(compte.is_staff or compte.is_superuser)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn('Ne recréez pas les classes', message.body)
        self.assertIn('aucune saisie ultérieure', message.body)
        self.assertNotIn('La trame de départ est prête', message.body)
        self.assertNotIn('Créer une classe', message.body)
        self.assertEqual(message.alternatives[0].mimetype, 'text/html')
        lien = next(l for l in message.body.splitlines() if l.startswith('https://'))
        self.assertNotIn(lien, sortie)
        jeton = lien.rstrip('/').split('/')[-1]
        self.assertTrue(default_token_generator.check_token(compte, jeton))
        reponse = self.client.get(lien.removeprefix('https://ecole.example.invalid'))
        self.assertEqual(reponse.status_code, 302)
        reponse = self.client.post(reponse.url, {'new_password1': 'Personnel!Import2026UnePhrase',
                                                'new_password2': 'Personnel!Import2026UnePhrase'})
        self.assertEqual(reponse.status_code, 302)
        compte.refresh_from_db()
        self.assertTrue(compte.check_password('Personnel!Import2026UnePhrase'))
        self.assertFalse(default_token_generator.check_token(compte, jeton))
        empreinte = compte.password
        comptes, classes = Utilisateur.objects.count(), m.Classe.objects.count()
        self.renvoyer()
        compte.refresh_from_db()
        self.assertEqual(compte.password, empreinte)
        self.assertEqual(Utilisateur.objects.count(), comptes)
        self.assertEqual(m.Classe.objects.count(), classes)
        self.assertEqual(len(mail.outbox), 2)
        for audit in m.EvenementAudit.objects.filter(action__startswith='ecole.import_accueil'):
            self.assertNotIn(jeton, str(audit.nouvelles_valeurs))

    def test_echec_transport_conserve_import_puis_renvoi(self):
        secret = 'https://ecole.example.invalid/jeton-prive-fictif/'
        with patch('suivi.courriels_comptes.EmailMultiAlternatives.send', side_effect=OSError(secret)):
            with self.assertRaisesMessage(CommandError, 'Ne pas réimporter') as erreur:
                self.ouvrir()
        self.assertNotIn(secret, str(erreur.exception))
        ecole = m.Ecole.objects.get(nom='École importée fictive')
        self.assertTrue(Utilisateur.objects.filter(username='direction-import-mail').exists())
        evenement = m.EvenementAudit.objects.get(ecole=ecole, action='ecole.import_accueil_echec')
        self.assertEqual(evenement.nouvelles_valeurs['erreur'], 'OSError')
        self.assertNotIn(secret, str(evenement.nouvelles_valeurs))
        self.renvoyer()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(m.Ecole.objects.count(), 3)
        self.assertTrue(m.EvenementAudit.objects.filter(ecole=ecole, action='ecole.import_accueil_envoye').exists())

    def test_envoi_zero_est_un_echec_et_aucun_mail_avant_commit(self):
        with patch('suivi.courriels_comptes.EmailMultiAlternatives.send', return_value=0):
            with self.assertRaisesMessage(CommandError, 'envoi non confirmé'):
                self.ouvrir()
        compte = Utilisateur.objects.get(username='direction-import-mail')
        ecole = m.Ecole.objects.get(nom='École importée fictive')
        with transaction.atomic(), self.assertRaisesMessage(CommandError, 'après validation'):
            envoyer_accueil_import(ecole=ecole, direction=compte, operateur=self.direction,
                                  url='https://ecole.example.invalid')
        self.assertEqual(len(mail.outbox), 0)

    def test_panne_import_ne_cree_ni_compte_ni_courriel(self):
        with patch('suivi.imports_ecole.shutil.copyfileobj', side_effect=OSError('panne fictive')):
            with self.assertRaises(CommandError):
                self.ouvrir()
        self.assertFalse(Utilisateur.objects.filter(username='direction-import-mail').exists())
        self.assertEqual(m.Ecole.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)

    def test_options_invalides_et_adresse_existante_refusees_avant_creation(self):
        for options in ({'email': ' '}, {'url': 'http://ecole.example.invalid'},
                        {'url': 'https://ecole.example.invalid/chemin/'},
                        {'url': 'https://ecole.example.invalid:invalide'},
                        {'url': 'https://ecole.example.invalid\n'},
                        {'email': self.direction.email}, {'creer_direction': False},
                        {'email': None}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.ouvrir(**options)
        for backend in ('django.core.mail.backends.console.EmailBackend',
                        'django.core.mail.backends.filebased.EmailBackend',
                        'django.core.mail.backends.dummy.EmailBackend'):
            with override_settings(EMAIL_BACKEND=backend), self.assertRaises(CommandError):
                self.ouvrir()
        with override_settings(EMAIL_DISPONIBLE=False), self.assertRaises(CommandError):
            self.ouvrir()
        self.assertEqual(m.Ecole.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)

    def test_renvoi_refuse_compte_existant_operateur_ordinaire_et_direction_retiree(self):
        self.ouvrir()
        with self.assertRaises(CommandError):
            self.renvoyer(direction=self.direction.username)
        with self.assertRaises(CommandError):
            self.renvoyer(operateur=self.prof.username)
        compte = Utilisateur.objects.get(username='direction-import-mail')
        ResponsabiliteEcole.objects.filter(appartenance__utilisateur=compte).update(etat='terminee')
        with self.assertRaisesMessage(CommandError, 'direction active'):
            self.renvoyer()
        self.assertEqual(len(mail.outbox), 1)
