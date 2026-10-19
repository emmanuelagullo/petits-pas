"""École 0.10 fictive complète : reprise, export 0.8.0, reprise et migration."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile
from suivi.paquet_local import creer_sauvegarde, preparer_restauration

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT/'scripts/fixtures/ecole-fictive-0.10.zip'
NOTICE = json.loads(FIXTURE.with_suffix('.json').read_text(encoding='utf-8'))


def empreinte(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contenu(paquet):
    with closing(sqlite3.connect(paquet/'carnet.sqlite3')) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise AssertionError('Intégrité SQLite')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise AssertionError('Relations SQLite')
        donnees = '\n'.join(db.iterdump())
    return donnees, {p.relative_to(paquet).as_posix(): empreinte(p)
        for p in paquet.rglob('*') if p.is_file() and p.name != 'carnet.sqlite3'}


class ArchiveHistoriqueTests(unittest.TestCase):
    def test_ecole_complete_restauree_reexportee_et_migree_sans_changer_original(self):
        self.assertEqual(empreinte(FIXTURE), NOTICE['sha256'])
        with ZipFile(FIXTURE) as archive:
            self.assertNotIn('application', json.loads(archive.read('manifest.json')))
        with tempfile.TemporaryDirectory(prefix='qualification-archive-') as temp:
            parent = Path(temp)
            copie = preparer_restauration(FIXTURE, parent).etape
            with closing(sqlite3.connect(copie/'carnet.sqlite3')) as db:
                for table, nombre in NOTICE['attendus'].items():
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], nombre)
            avant = contenu(copie)
            self.assertEqual(len([n for n in avant[1] if n.startswith('media/')]), NOTICE['medias'])
            export = parent/'nouvel-export.zip'
            creer_sauvegarde(copie, export)
            self.assertEqual(contenu(copie), avant)
            with ZipFile(export) as archive:
                self.assertEqual(json.loads(archive.read('manifest.json'))['application'], 'petits-pas')
            reprise = preparer_restauration(export, parent).etape
            self.assertEqual(contenu(reprise), avant)
            # Seule la seconde copie est confiée au Django courant ; jamais l'original.
            env = {k: v for k, v in os.environ.items()
                if not k.startswith(('CARNET_', 'DATABASE_', 'DJANGO_'))}
            env.update(DATABASE_URL='', CARNET_SQLITE_PATH=str(reprise/'carnet.sqlite3'),
                CARNET_MEDIA_ROOT=str(reprise/'media'), CARNET_SECRET_KEY='cle-fictive-qualification',
                CARNET_ANTIBRUTEFORCE='non', CARNET_EMAIL_DESACTIVE='oui')
            subprocess.run([sys.executable, str(ROOT/'manage.py'), 'migrate', '--noinput'],
                cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
            # Les modèles scolaires et migrations n'ont pas changé depuis 0.10.
            self.assertEqual(contenu(reprise), avant)
        self.assertEqual(empreinte(FIXTURE), NOTICE['sha256'])
