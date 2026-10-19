#!/usr/bin/env python3
"""Qualifier les facteurs sur une vraie SQLite temporaire, jamais une base d'école."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix='petits-pas-totp-') as temp:
        dossier = Path(temp)
        (dossier/'qualification_totp.py').write_text(
            'from carnet.settings_tests import *\n'
            'import os\n'
            'DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",\n'
            ' "NAME": os.environ["TOTP_BASE"], "TEST": {"NAME": os.environ["TOTP_TEST_BASE"]}}}\n')
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'qualification_totp',
            'TOTP_BASE': str(dossier/'base.sqlite3'), 'TOTP_TEST_BASE': str(dossier/'test.sqlite3'),
            'PYTHONPATH': os.pathsep.join([str(dossier), str(ROOT), os.environ.get('PYTHONPATH', '')])}
        subprocess.run([sys.executable, str(ROOT/'manage.py'), 'test',
            'comptes.tests_totp', 'comptes.tests_totp_concurrence',
            '--noinput'], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    main()
