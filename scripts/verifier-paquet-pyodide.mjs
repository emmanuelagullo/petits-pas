import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
// Sonde fictive du vrai runtime : conserve le témoin historique publié.
const root=fileURLToPath(new URL('../',import.meta.url));
const bundle=path.resolve(process.env.PWA_BUNDLE||path.join(root,'dist/pwa'));
const config=JSON.parse(fs.readFileSync(bundle+'/config.json'));
const {loadPyodide}=await import(pathToFileURL(bundle+'/runtime/pyodide.mjs'));
const p=await loadPyodide({indexURL:bundle+'/runtime/'});
await p.loadPackage(['micropip','pycryptodome','pillow','pyyaml']);
for(const nom of config.wheels)p.FS.writeFile('/tmp/'+nom,fs.readFileSync(bundle+'/wheels/'+nom));
await p.runPythonAsync(`import micropip\nawait micropip.install(${JSON.stringify(config.wheels.map(n=>'emfs:/tmp/'+n))})`);
p.unpackArchive(new Uint8Array(fs.readFileSync(bundle+'/application.zip')),'zip',{extractDir:'/application'});
p.FS.writeFile('/tmp/historique.zip',fs.readFileSync(root+'/scripts/fixtures/ecole-fictive-0.10.zip'));
p.runPython(`import sys;sys.path.insert(0,'/application')
from pwa import bridge as b
b.initialize('https://ecole-fictive.example','test','/ecole/')
from suivi import paquet_local as paquet
from suivi.paquet_local import restauration_en_attente as attente_vue
from pathlib import Path
from django.db.migrations.loader import MigrationLoader
from django.db import connections
import sqlite3
copie=paquet.preparer_restauration(Path('/tmp/historique.zip'),Path('/'),migrations_connues=MigrationLoader(None).disk_migrations)
paquet.retenir_preparation(copie)
paquet.confirmer_restauration()
assert attente_vue() is not None
assert b.apply_pending_restore()
assert attente_vue() is None
from suivi.models import Ecole
assert Ecole.objects.exists()
with sqlite3.connect('/data/carnet.sqlite3') as db:
 assert db.execute('PRAGMA foreign_key_check').fetchone() is None
 assert db.execute('SELECT count(*) FROM django_session').fetchone()[0]==0
from django.db.migrations.executor import MigrationExecutor
assert not MigrationExecutor(connections['default']).migration_plan(MigrationExecutor(connections['default']).loader.graph.leaf_nodes())
`);
console.log('Petits Pas WASM : archive 0.10 → préparation → activation → migrations → sessions fermées et façade rechargée : OK');
