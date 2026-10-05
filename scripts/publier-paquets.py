#!/usr/bin/env python3
"""Publier sur GitHub les artefacts exacts d'une construction de tag réussie."""
import argparse
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile
from publication import TAG, verify, sha256

DEPOT = 'emmanuelagullo/petits-pas'
FORGES = ['https://github.com/' + DEPOT + '.git', 'https://gitlab.inria.fr/petits-pas/petits-pas.git']
WORKFLOW = '.github/workflows/paquets-locaux.yml'


def gh(*args, **kwargs):
    return subprocess.run(['gh', *args], check=True, **kwargs)


def api(path):
    return json.loads(gh('api', 'repos/' + DEPOT + '/' + path, capture_output=True, text=True).stdout)


def verify_run(run, tag):
    if (run.get('conclusion') != 'success' or run.get('status') != 'completed'
            or run.get('path') != WORKFLOW or run.get('head_branch') != tag
            or run.get('event') not in ('push', 'workflow_dispatch')):
        raise ValueError('Choisir une construction réussie du tag, avec le workflow des programmes.')
    import re
    if not re.fullmatch(r'[a-f0-9]{40}', run.get('head_sha', '')):
        raise ValueError('Commit de construction invalide.')
    return run['head_sha']


def verify_tags(tag, commit):
    for forge in FORGES:
        lines = subprocess.check_output(['git', 'ls-remote', '--tags', forge, 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], text=True, timeout=60).splitlines()
        reverse = {ref: sha for sha, ref in (line.split('\t') for line in lines)}
        if reverse.get('refs/tags/' + tag + '^{}', reverse.get('refs/tags/' + tag)) != commit:
            raise ValueError('Tag absent ou différent sur ' + forge)


def unpack(archive, folder):
    with ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if len(entries) > 20 or sum(x.file_size for x in entries) > 1024**3:
            raise ValueError('Artefact trop volumineux.')
        for entry in entries:
            name = entry.filename
            if entry.is_dir() or Path(name).name != name or '/' in name or '\\' in name or name in ('.', '..') or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Chemin non autorisé dans un artefact.')
            destination = folder / name
            contents = zipped.read(entry)
            if destination.exists():
                if destination.read_bytes() != contents:
                    raise ValueError('Fichier divergent entre artefacts : ' + name)
            else:
                destination.write_bytes(contents)


def prepare(run_id, tag, folder):
    run = api('actions/runs/' + run_id)
    commit = verify_run(run, tag)
    verify_tags(tag, commit)
    artifacts = []
    page = 1
    while True:
        batch = api(f'actions/runs/{run_id}/artifacts?per_page=100&page={page}')['artifacts']
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    extracted = {}
    for name in ('PetitsPas-linux', 'PetitsPas-windows', 'PetitsPas-Setup-windows'):
        candidates = [a for a in artifacts if a['name'] == name]
        if len(candidates) != 1 or candidates[0]['expired']:
            raise ValueError('Artefact absent, ambigu ou expiré : ' + name)
        artifact = candidates[0]
        archive = folder / (name + '.artifact.zip')
        with archive.open('wb') as stream:
            gh('api', f'repos/{DEPOT}/actions/artifacts/{artifact["id"]}/zip', stdout=stream)
        if artifact.get('digest') and artifact['digest'] != 'sha256:' + sha256(archive):
            raise ValueError('Empreinte de l’artefact différente : ' + name)
        destination = folder / name
        destination.mkdir()
        unpack(archive, destination)
        extracted[name] = destination
        archive.unlink()
    setup_name = f'PetitsPas-Setup-{tag}-x64.exe'
    setup = extracted['PetitsPas-Setup-windows'] / setup_name
    combined_setup = extracted['PetitsPas-windows'] / setup_name
    if combined_setup.exists() and combined_setup.read_bytes() != setup.read_bytes():
        raise ValueError('Fichier divergent entre artefacts : ' + setup_name)
    if not combined_setup.exists():
        shutil.copyfile(setup, combined_setup)
    manifests = []
    for name, target, expected in [('linux', 'linux-ubuntu24.04-x86_64', {'PetitsPas-linux.tar.gz', 'notes-version.md'}),
                                 ('windows', 'windows-x64', {'PetitsPas-windows.zip', f'PetitsPas-Setup-{tag}-x64.exe', 'notes-version.md'})]:
        source = extracted['PetitsPas-' + name]
        path = source / ('publication-' + name + '.json')
        record = json.loads(path.read_text())
        if (record['ci']['provider'] != 'github' or str(record['ci']['run']) != run_id
                or str(record['ci']['attempt']) != str(run['run_attempt']) or record['ci']['job'] != name):
            raise ValueError('Manifeste issu d’une autre exécution ou tentative.')
        if verify(record, source, commit, tag, 'programme', target) != expected:
            raise ValueError('Liste de fichiers inattendue.')
        # Les octets du candidat sont vérifiés avant toute comparaison des notes.
        for filename in expected - {'notes-version.md'}:
            shutil.copyfile(source / filename, folder / filename)
        destination = folder / path.name
        shutil.copyfile(path, destination)
        manifests.append(destination)
    linux_notes = (extracted['PetitsPas-linux'] / 'notes-version.md').read_bytes()
    windows_notes = (extracted['PetitsPas-windows'] / 'notes-version.md').read_bytes()
    if linux_notes.replace(b'\r\n', b'\n') != windows_notes.replace(b'\r\n', b'\n'):
        raise ValueError('Fichier divergent entre artefacts : notes-version.md')
    # La note commune conserve les octets Linux ; garder aussi l’original Windows
    # si ses fins de ligne diffèrent, pour retrouver les empreintes du manifeste.
    (folder / 'notes-version.md').write_bytes(linux_notes)
    extra_notes = []
    if windows_notes != linux_notes:
        original = folder / 'notes-version-windows.md'
        original.write_bytes(windows_notes)
        extra_notes.append(original)
    # Une réexécution pendant le téléchargement ne doit pas changer le candidat.
    current = api('actions/runs/' + run_id)
    if verify_run(current, tag) != commit or current['run_attempt'] != run['run_attempt']:
        raise ValueError('Construction modifiée pendant le téléchargement.')
    files = [folder / 'PetitsPas-linux.tar.gz', folder / 'PetitsPas-windows.zip', folder / f'PetitsPas-Setup-{tag}-x64.exe', *manifests, folder / 'notes-version.md', *extra_notes]
    (folder / 'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in files), encoding='utf-8')
    return files + [folder / 'SHA256SUMS'], commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=int)
    parser.add_argument('tag')
    args = parser.parse_args()
    if args.run <= 0 or not TAG.fullmatch(args.tag):
        parser.error('Exécution positive et tag numérique requis.')
    with tempfile.TemporaryDirectory(prefix='petits-pas-release-') as temp:
        folder = Path(temp)
        files, commit = prepare(str(args.run), args.tag, folder)
        if subprocess.run(['gh', 'release', 'view', args.tag, '--repo', DEPOT], capture_output=True).returncode == 0:
            raise ValueError('Cette release existe déjà ; aucun fichier ne sera remplacé.')
        notes = folder / 'release.md'
        notes.write_text((folder / 'notes-version.md').read_text(encoding='utf-8') + f'\nCode : `{commit}`. Construction : https://github.com/{DEPOT}/actions/runs/{args.run}\n\nWindows x64 et Ubuntu 24.04 x86-64. Les données de l’école restent séparées du programme.\n', encoding='utf-8')
        print('Publication des fichiers vérifiés :', args.tag, commit, flush=True)
        gh('release', 'create', args.tag, *map(str, files), '--repo', DEPOT, '--verify-tag', '--draft', '--prerelease', '--latest=false', '--title', 'Petits Pas ' + args.tag, '--notes-file', str(notes))
        downloaded = folder / 'uploaded'; downloaded.mkdir()
        gh('release', 'download', args.tag, '--repo', DEPOT, '--dir', str(downloaded))
        for file in files:
            if sha256(file) != sha256(downloaded / file.name):
                raise ValueError('Fichier chargé différent ; le brouillon reste à examiner.')
        gh('release', 'edit', args.tag, '--repo', DEPOT, '--draft=false')
        print('Release GitHub publiée. La publication PWA reste indépendante.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit('Publication refusée : ' + str(error))
