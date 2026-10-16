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
const dependances=config.wheels.filter(n => /^(django|asgiref|sqlparse)-/i.test(n));
if (dependances.length !== 3) throw new Error('Django et ses dépendances pures sont requis');
for (const wheel of [nom, ...dependances]) {
  python.FS.writeFile('/tmp/'+wheel,fs.readFileSync(racine+'wheels/'+wheel));
}
await python.runPythonAsync(`
import micropip
await micropip.install(${JSON.stringify(['emfs:/tmp/'+nom, ...dependances.map(n=>'emfs:/tmp/'+n)])})
from django.conf import settings
settings.configure(SECRET_KEY='cle-fictive-pyodide')
from django.core.exceptions import PermissionDenied, ValidationError
from pas_communs.authentification.mots_de_passe import MaximumLengthValidator, PlafondMotDePasse
from pas_communs.authentification.sessions import connexion_recente
from pas_communs.authentification.totp import uri_otpauth
MaximumLengthValidator().validate('x'*1024)
try:
    MaximumLengthValidator().validate('x'*1025)
except ValidationError:
    pass
else:
    raise AssertionError('Plafond absent')
try:
    PlafondMotDePasse().authenticate(None, password='x'*1025)
except PermissionDenied:
    pass
else:
    raise AssertionError('Protection avant hachage absente')
assert connexion_recente({'connexion_le': 1000}, maintenant=1100)
assert 'otpauth://' in uri_otpauth('compte-fictif', b'cle-fictive', emetteur='Petits Pas')
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
print('Wheel installe par micropip dans Pyodide, primitives auth, SQLite backup et ZIP aller-retour : OK')
`);
