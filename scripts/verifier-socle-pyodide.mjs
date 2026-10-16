// Vérifier le wheel réellement embarqué, sans navigateur ni données utilisateur.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const dossier = new URL('../dist/pwa/', import.meta.url);
const racine = fileURLToPath(dossier);
const { loadPyodide } = await import(new URL('runtime/pyodide.mjs', dossier));
const python = await loadPyodide({indexURL: racine+'runtime/'});
await python.loadPackage('micropip');
const config=JSON.parse(fs.readFileSync(new URL('config.json', dossier), 'utf8'));
const candidats=config.wheels.filter(n => n.startsWith('pas_communs-'));
if (candidats.length !== 1) throw new Error('Un seul wheel Pas communs est requis');
const nom=candidats[0];
python.FS.writeFile('/tmp/'+nom,fs.readFileSync(racine+'wheels/'+nom));
await python.runPythonAsync(`
import micropip
await micropip.install('emfs:/tmp/${nom}')
from pas_communs.paquets import ProfilPaquet, creer_sauvegarde, preparer_restauration, iterer_restauration
from pathlib import Path
from contextlib import closing
import sqlite3, tempfile
from io import BytesIO
with tempfile.TemporaryDirectory() as t:
    parent=Path(t)
    paquet=parent/'source'; paquet.mkdir()
    (paquet/'secret-key').write_text('cle-fictive-pyodide')
    with closing(sqlite3.connect(paquet/'base.sqlite3')) as db,db:
        db.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
        db.execute('CREATE TABLE fictif (valeur TEXT)')
        db.execute("INSERT INTO fictif VALUES ('conserve')")
    profil=ProfilPaquet('neutre','format-neutre','base.sqlite3')
    archive=BytesIO()
    creer_sauvegarde(paquet,archive,profil=profil,taille_bloc=4096)
    copie=preparer_restauration(archive,parent,profil=profil)
    with closing(sqlite3.connect(copie.etape/'base.sqlite3')) as db:
        assert db.execute('SELECT valeur FROM fictif').fetchone()[0]=='conserve'
print('Wheel installe par micropip dans Pyodide, SQLite backup et ZIP aller-retour : OK')
`);
