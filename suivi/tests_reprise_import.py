"""Interruption fictive et protection des imports validés/référencés."""
import io
import json
import subprocess
import sys

from django.core.management import call_command, CommandError
from django.test import TransactionTestCase, override_settings

from . import tests_imports_ecole
from .imports_ecole import verifier_zip
from .reprise_import import verrou_imports, journaliser, diagnostiquer, nettoyer
from . import models as m


@override_settings(ENVIRONNEMENT_EPHEMERE=False, ENVIRONNEMENT_ATELIER=False)
class RepriseImportTests(TransactionTestCase):
    def setUp(self):
        tests_imports_ecole.ImportEcoleTests.setUp(self)

    def abandon(self, identifiant='a'*32):
        with verrou_imports() as racine:
            journaliser(racine, identifiant, etat='commence', sha256='0'*64)
            destination = racine / identifiant
            destination.mkdir()
            (destination / 'photo.bin').write_bytes(b'realisation-fictive')
        return racine, identifiant

    def test_arret_processus_libere_verrou_et_permet_nettoyage_cible(self):
        racine, identifiant = self.abandon()
        script = """
import fcntl,sys
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    print('verrouille', flush=True)
    sys.stdin.read()
"""
        enfant = subprocess.Popen([sys.executable, '-c', script, str(racine / '.verrou')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(enfant.stdout.readline().strip(), 'verrouille')
            with self.assertRaisesMessage(CommandError, 'déjà en cours'):
                call_command('recuperer_imports_ecoles', stdout=io.StringIO())
        finally:
            enfant.kill()
            enfant.communicate(timeout=10)
        autre = racine / ('b'*32)
        autre.mkdir()
        (autre / 'intact').write_bytes(b'intact')
        sortie = io.StringIO()
        call_command('recuperer_imports_ecoles', stdout=sortie)
        self.assertIn('abandonne', sortie.getvalue())
        self.assertTrue((racine / identifiant).exists())
        call_command('recuperer_imports_ecoles', nettoyer=identifiant,
            operateur=self.direction.username, stdout=io.StringIO())
        self.assertFalse((racine / identifiant).exists())
        self.assertTrue((autre / 'intact').exists())
        self.assertEqual(json.loads((racine / (identifiant+'.json')).read_text())['etat'], 'nettoye')
        # Nettoyage idempotent, sans suppression des anciennes copies sans journal.
        call_command('recuperer_imports_ecoles', nettoyer=identifiant,
            operateur=self.direction.username, stdout=io.StringIO())

    def test_import_valide_protege_meme_si_journal_commence_et_accueil_absent(self):
        with verifier_zip(self.archive, self.root) as projection:
            ecole = projection.importer(self.compte, 'Import fictif', '', self.direction)
        audit = m.EvenementAudit.objects.get(ecole=ecole, action='ecole.import_zip')
        identifiant = audit.nouvelles_valeurs['medias_prefixe'].split('/')[1]
        with verrou_imports() as racine:
            bilan = diagnostiquer(racine, identifiant)
            self.assertEqual(bilan['etat'], 'importe')
            self.assertEqual(bilan['ecole_id'], ecole.pk)
            self.assertEqual(bilan['accueil'], 'non_confirme')
            with self.assertRaises(CommandError):
                nettoyer(racine, identifiant)
            m.EvenementAudit.objects.create(ecole=ecole, acteur=self.direction, action='ecole.import_accueil_envoye',
                nouvelles_valeurs={'direction_id': self.compte.pk})
            self.assertEqual(diagnostiquer(racine, identifiant)['accueil'], 'envoi_audite')

    def test_reference_json_ou_fichier_sans_audit_interdit_nettoyage(self):
        racine, identifiant = self.abandon()
        self.trace.photo = f'imports/{identifiant}/photo.bin'
        self.trace.save(update_fields=['photo'])
        with verrou_imports():
            self.assertFalse(diagnostiquer(racine, identifiant)['nettoyable'])
        self.trace.photo = ''
        self.trace.save(update_fields=['photo'])
        m.EvenementAudit.objects.create(ecole=self.ecole, acteur=self.direction, action='test.fictif',
            nouvelles_valeurs={'imbrique': [{f'imports/{identifiant}/photo.bin': 'reference'}]})
        with verrou_imports():
            with self.assertRaises(CommandError):
                nettoyer(racine, identifiant)

    def test_refus_operateur_chemin_symbolique_et_journal_invalide(self):
        racine, identifiant = self.abandon()
        with self.assertRaises(CommandError):
            call_command('recuperer_imports_ecoles', nettoyer=identifiant,
                operateur=self.compte.username, stdout=io.StringIO())
        with verrou_imports():
            for mauvais in ('../autre', 'a'*31, 'A'*32):
                with self.assertRaises(CommandError):
                    nettoyer(racine, mauvais)
            (racine / identifiant / 'lien').symlink_to(self.archive)
            with self.assertRaises(CommandError):
                nettoyer(racine, identifiant)
            (racine / (identifiant+'.json')).write_text('{}')
            with self.assertRaises(CommandError):
                nettoyer(racine, identifiant)
