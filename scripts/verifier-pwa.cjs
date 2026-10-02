#!/usr/bin/env node
// Essais navigateur réels sur un bundle --test et un profil temporaire fictif.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../dist/pwa');
const requirePwa = createRequire(path.resolve(__dirname, '../pwa/package.json'));
const playwright = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')) : requirePwa('playwright');
const types = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm', '.css': 'text/css', '.svg': 'image/svg+xml'};
const network = [];
const server = http.createServer((req, res) => {
  const name = new URL(req.url, 'http://localhost').pathname;
  network.push(name);
  const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name));
  if (!file.startsWith(root + path.sep)) {res.writeHead(403).end(); return;}
  try {
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    res.end(fs.readFileSync(file));
  } catch {res.writeHead(404).end('Ressource absente');}
});
let browser;
let currentPage;
const report = [];
function pass(test, data = {}) { report.push({test, ...data}); console.log('OK', test, JSON.stringify(data)); }
async function boot(page, url) {
  await page.goto(url);
  await page.waitForFunction(() => !!window.pwaTest || /TypeError|PythonError|Error:/.test(document.querySelector('#status').textContent), null, {timeout: 120000});
  const status = await page.locator('#status').innerText();
  assert(!/Error/.test(status), status);
  await page.frameLocator('#app').locator('h1').waitFor({timeout: 60000});
}
async function python(page, code, failpoint) {
  const value = await page.evaluate(args => window.pwaTest({kind: 'test-python', ...args}), {code, failpoint});
  return value.result;
}
async function login(page) {
  const frame = page.frameLocator('#app');
  await frame.locator('[name="nom_utilisateur"]').fill('direction-fictive');
  await frame.locator('[name="mot_de_passe"]').fill('Test-fictif-PWA-2026!');
  await frame.getByRole('button', {name: 'Entrer', exact: true}).click();
  await frame.locator('h1').filter({hasText: 'Les classes'}).waitFor({timeout: 30000});
}
(async () => {
  assert(JSON.parse(fs.readFileSync(path.join(root, 'config.json'))).testMode, 'Reconstruire avec --test');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/`;
  browser = await playwright.chromium.launch({headless: true,
    ...(process.env.PWA_CHROMIUM ? {executablePath: process.env.PWA_CHROMIUM} : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage']});
  const context = await browser.newContext({acceptDownloads: true});
  const page = await context.newPage();
  currentPage = page;
  page.on('console', message => { if (message.type() === 'error' || message.type() === 'warning') console.error('CONSOLE', message.text()); });
  page.on('pageerror', error => console.error('PAGE', error.message));
  const started = performance.now();
  await boot(page, url);
  pass('Django, migrations, pont SW/WSGI et installation', {coldMs: Math.round(performance.now() - started)});
  const frame = page.frameLocator('#app');
  for (const [name, value] of Object.entries({ecole_nom: 'École fictive PWA', commune: 'Commune fictive', first_name: 'Nadia', last_name: 'Fictive', username: 'direction-fictive', password1: 'Test-fictif-PWA-2026!', password2: 'Test-fictif-PWA-2026!'})) {
    await frame.locator(`[name="${name}"]`).fill(value);
  }
  await frame.getByRole('button', {name: 'Créer l’école et mon compte'}).click();
  await frame.getByRole('heading', {name: "Gérer l'école", exact: true}).waitFor({timeout: 30000});
  pass('Formulaire installation, CSRF et session virtuelle');
  const ids = JSON.parse(await python(page, `
import json
from suivi.models import Ecole, Classe, Eleve, Scolarite, Competence
from comptes.models import Utilisateur, AppartenanceEcole, AffectationClasse
ecole = Ecole.objects.get()
classe = Classe.objects.create(ecole=ecole, nom='Classe fictive', annee_scolaire='2026-2027')
appartenance = AppartenanceEcole.objects.get(utilisateur__username='direction-fictive')
AffectationClasse.objects.create(appartenance=appartenance, classe=classe, type='responsable')
classe.activer()
eleve = Eleve.objects.create(ecole=ecole, prenom='Ana', nom='Fictive')
Scolarite.objects.create(eleve=eleve, classe=classe, annee_scolaire='2026-2027', niveau='MS')
competence = Competence.objects.filter(domaine__ecole=ecole).first()
json.dumps({'eleve': eleve.pk, 'competence': competence.pk, 'classe': classe.pk})
`));
  await page.locator('#app').evaluate((node, route) => {node.src = route;}, `/app/eleve/${ids.eleve}/`);
  const button = frame.locator(`#c${ids.competence} button.bascule`);
  await button.waitFor({timeout: 30000});
  await button.click();
  await page.waitForFunction(() => document.querySelector('#app').contentDocument.querySelector('button[data-statut="reussi"]'));
  assert.equal(await python(page, "from suivi.models import Observation; Observation.objects.get().statut"), 'reussi');
  pass('Saisie HTMX réelle et ORM');
  const forbidden = await page.evaluate(async ({route}) => {
    const response = await fetch(route, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'csrfmiddlewaretoken=invalide'});
    return response.status;
  }, {route: `/app/eleve/${ids.eleve}/competence/${ids.competence}/basculer/`});
  assert.equal(forbidden, 403);
  pass('CSRF invalide refusé');
  await page.locator('#app').evaluate((node, route) => {node.src = route;}, `/app/eleve/${ids.eleve}/competence/${ids.competence}/trace/`);
  await frame.locator('[name="commentaire"]').fill('Réalisation entièrement fictive.');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6WQAAAAASUVORK5CYII=', 'base64');
  await frame.locator('[name="photo"]').setInputFiles({name: 'realisation-fictive.png', mimeType: 'image/png', buffer: png});
  await frame.getByRole('button', {name: 'Ajouter la trace', exact: true}).click();
  await frame.getByText('Trace enregistrée pour Ana.', {exact: true}).waitFor({timeout: 30000});
  const media = JSON.parse(await python(page, `
from suivi.models import Trace
trace = Trace.objects.get()
json.dumps({'id': trace.pk, 'photo': trace.photo.name, 'commentaire': trace.commentaire})
`));
  assert.equal(media.commentaire, 'Réalisation entièrement fictive.');
  assert(media.photo.endsWith('.png'));
  const photoResponse = await page.evaluate(async route => {const r=await fetch(route);return {status:r.status,bytes:(await r.arrayBuffer()).byteLength};}, `/app/media/trace/${media.id}/`);
  assert.equal(photoResponse.status, 200); assert(photoResponse.bytes > 20);
  pass('Upload multipart Pillow et média autorisé local');
  await page.frames()[1].goto(url + 'app/gestion/sauvegardes-locales/');
  const downloadReady = page.waitForEvent('download');
  await page.frameLocator('#app').getByRole('button', {name: 'Télécharger une sauvegarde', exact: true}).click();
  const download = await downloadReady;
  const archivePath = await download.path();
  const {execFileSync} = require('node:child_process');
  execFileSync('python3', ['-c', "import sys,zipfile,json,hashlib; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read('manifest.json')); assert m['format']=='petits-pas-paquet'; assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in m['files'].items()); assert any(n.startswith('media/') for n in m['files'])", archivePath]);
  pass('Export ZIP commun au mode autonome, manifeste et photos vérifiés');

  const second = await context.newPage();
  await second.goto(url);
  await second.locator('#status').filter({hasText: 'déjà ouvert'}).waitFor();
  await second.close(); pass('Deuxième onglet refusé');
  // Coupure de la connexion : ressources et requêtes applicatives restent locales.
  await context.setOffline(true);
  const hotStarted = performance.now();
  await boot(page, url);
  await login(page);
  assert.equal(await python(page, "from suivi.models import Trace; Trace.objects.get().photo.name"), media.photo);
  pass('Relance hors ligne, réauthentification et photo conservée', {hotMs: Math.round(performance.now() - hotStarted)});
  // Injection au point exact après écriture/flush OPFS, avant pointeur actif.
  await assert.rejects(python(page, "Ecole.objects.update(nom='Écriture non confirmée')", 'before-activate'));
  await assert.rejects(python(page, "Ecole.objects.count()"));
  await boot(page, url);
  assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
  pass('Interruption avant activation : état précédent retrouvé, runtime bloqué après échec');
  await assert.rejects(python(page, "Ecole.objects.update(nom='Quota fictif')", 'quota'));
  await boot(page, url);
  assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
  assert.equal(await python(page, "import sqlite3; db=sqlite3.connect('/data/carnet.sqlite3'); str((db.execute('PRAGMA quick_check').fetchone(), db.execute('PRAGMA foreign_key_check').fetchall()))"), "(('ok',), [])");
  pass('Quota simulé et intégrité SQLite après reprise');
  await page.close();
  const reopened = await context.newPage(); currentPage = reopened;
  await boot(reopened, url);
  assert.equal(await python(reopened, "from suivi.models import Trace; Trace.objects.get().photo.name"), media.photo);
  pass('Fermeture de la page propriétaire puis réouverture hors ligne');
  assert(!network.some(route => route.startsWith('/app/')), 'Une requête métier est sortie vers le serveur statique');
  pass('Aucune requête métier sur le réseau');
  fs.writeFileSync(path.join(root, 'resultats-tests.json'), JSON.stringify(report, null, 2));
})().catch(async error => {
  console.error(error);
  if (currentPage) {
    console.error('STATUS', await currentPage.locator('#status').innerText());
    for (const frame of currentPage.frames()) console.error('FRAME', frame.url(), (await frame.locator('body').innerText().catch(() => '')).slice(0, 4000));
  }
  process.exitCode = 1;
}).finally(async () => {if(browser) await browser.close(); server.close();});
