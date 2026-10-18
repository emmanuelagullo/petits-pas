"""Identité et intégrité des candidats publics ; aucune donnée d'école réelle."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def git(*arguments):
    try:
        return subprocess.check_output(['git', *arguments], cwd=ROOT, text=True, timeout=8).strip()
    except (OSError, subprocess.SubprocessError):
        return ''

FORMAT = 'petits-pas-publication'


from pas_communs.publication import TAG, sha256, decrire as describe
from pas_communs import publication as _publication


def identity():
    return _publication.identite(os.environ, lambda: git('rev-parse','HEAD'))


def release_notes(tag=None, text=None):
    text = (ROOT / 'CHANGELOG.org').read_text(encoding='utf-8') if text is None else text
    sections = list(re.finditer(r'^\* (.+)$', text, re.M))
    matches = [m for m in sections if (re.match(re.escape(tag) + r'(?:\s|$)', m[1]) if tag else m[1] in ('Unreleased', 'À venir'))]
    if len(matches) != 1:
        raise ValueError('Une rubrique unique du CHANGELOG.org est requise : ' + (tag or 'À venir') + '.')
    section = matches[0]
    end = next((m.start() for m in sections if m.start() > section.start()), len(text))
    notes = text[section.end():end].strip()
    if not notes:
        if tag:
            raise ValueError('Notes de version vides.')
        return 'Aucune nouvelle modification depuis la dernière version numérotée.\n'
    notes = re.sub(r'^([*]{2,}) (.+)$', lambda m: '#' * len(m[1]) + ' ' + m[2], notes, flags=re.M)
    notes = re.sub(r'\[\[([^\]]+)\]\[([^\]]+)\]\]', r'[\2](\1)', notes)
    notes = re.sub(r'=([^=\n]+)=', r'`\1`', notes)
    return notes + '\n'


def manifest(mode, target, files):
    return _publication.manifeste(FORMAT, identity(), mode, target, files, os.environ)


def verify(record, folder, commit=None, tag=None, mode=None, target=None):
    return _publication.verifier(record, folder, format=FORMAT,
        commit=commit, tag=tag, mode=mode, target=target)
