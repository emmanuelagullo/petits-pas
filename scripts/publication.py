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
TAG = re.compile(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-[A-Za-z0-9.-]+)?\Z')


def git(*arguments):
    try:
        return subprocess.check_output(['git', *arguments], cwd=ROOT, text=True, timeout=8).strip()
    except (OSError, subprocess.SubprocessError):
        return ''

FORMAT = 'petits-pas-publication'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity():
    commit = os.environ.get('CI_COMMIT_SHA') or os.environ.get('GITHUB_SHA') or git('rev-parse', 'HEAD')
    if not re.fullmatch(r'[a-fA-F0-9]{40,64}', commit or ''):
        raise ValueError('Commit de construction introuvable.')
    tag = os.environ.get('CI_COMMIT_TAG') or (os.environ.get('GITHUB_REF_NAME') if os.environ.get('GITHUB_REF_TYPE') == 'tag' else None)
    if tag and not TAG.fullmatch(tag):
        raise ValueError('Tag de version invalide.')
    return {'commit': commit.lower(), 'tag': tag, 'application_version': tag or 'dev.' + commit[:8].lower()}


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


def describe(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Fichier régulier requis : ' + str(path))
    return {'name': path.name, 'size': path.stat().st_size, 'sha256': sha256(path)}


def manifest(mode, target, files):
    result = {'format': FORMAT, 'schema': 1, **identity(), 'mode': mode, 'target': target,
        'built_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version.split()[0],
        'ci': {'provider': 'gitlab' if os.environ.get('CI_PIPELINE_ID') else 'github' if os.environ.get('GITHUB_RUN_ID') else 'local',
               'run': os.environ.get('CI_PIPELINE_ID') or os.environ.get('GITHUB_RUN_ID'),
               'job': os.environ.get('CI_JOB_ID') or os.environ.get('GITHUB_JOB'),
               'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')},
        'files': [describe(p) for p in files]}
    if len({f['name'] for f in result['files']}) != len(result['files']):
        raise ValueError('Noms de fichiers répétés.')
    return result


def verify(record, folder, commit=None, tag=None, mode=None, target=None):
    if record.get('format') != FORMAT or record.get('schema') != 1:
        raise ValueError('Manifeste de publication invalide.')
    for key, expected in [('commit', commit), ('tag', tag), ('mode', mode), ('target', target)]:
        if expected is not None and record.get(key) != expected:
            raise ValueError('Manifeste incompatible : ' + key)
    if tag and record.get('application_version') != tag:
        raise ValueError('Version embarquée différente du tag.')
    names = set()
    if not isinstance(record.get('files'), list) or not record['files']:
        raise ValueError('Liste des fichiers absente.')
    for entry in record['files']:
        name = entry['name']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name) or name in names:
            raise ValueError('Nom de fichier invalide ou répété.')
        names.add(name)
        if describe(Path(folder) / name) != entry:
            raise ValueError('Fichier altéré : ' + name)
    return names
