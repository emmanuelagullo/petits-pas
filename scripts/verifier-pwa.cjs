#!/usr/bin/env node
// Essais navigateur réels sur un bundle --test et un profil temporaire fictif.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const os = require('node:os');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../dist/pwa');
const requirePwa = createRequire(path.resolve(__dirname, '../pwa/package.json'));
const playwright = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')) : requirePwa('playwright');
const types = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm', '.css': 'text/css', '.svg': 'image/svg+xml'};
const base = process.env.PWA_BASE_PATH || '/';
const network = [];
let published = null;
let serverRoot = process.env.PWA_OLD_BUNDLE ? path.resolve(process.env.PWA_OLD_BUNDLE) : root;
const tls = process.env.PWA_TEST_HTTPS === 'oui';
let certificat;
if (tls) {
  certificat = fs.mkdtempSync(path.join(os.tmpdir(), 'petits-pas-tls-fictif-'));
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
    '-subj', '/CN=localhost', '-keyout', path.join(certificat, 'key.pem'),
    '-out', path.join(certificat, 'cert.pem')], {stdio: 'ignore'});
}
const serve = (req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  network.push(pathname);
  if (pathname === '/petits-pas/temoin.html') {res.setHeader('Content-Type', 'text/html'); res.end('<h1>Site Hugo fictif</h1>'); return;}
  if (!pathname.startsWith(base)) {res.writeHead(404).end('Hors PWA'); return;}
  const name = '/' + pathname.slice(base.length);
  if (published && ['/config.json', '/sw.js', '/application.zip'].includes(name)) {
    res.setHeader('Content-Type', types[path.extname(name)] || 'application/octet-stream');
    res.end(name === '/config.json' ? JSON.stringify(published.config) : name === '/sw.js' ? published.sw : published.application); return;
  }
  const file = path.resolve(serverRoot, '.' + (name === '/' ? '/index.html' : name));
  if (!file.startsWith(serverRoot + path.sep)) {res.writeHead(403).end(); return;}
  try {
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    res.end(fs.readFileSync(file));
  } catch {res.writeHead(404).end('Ressource absente');}
};
const server = tls ? https.createServer({key: fs.readFileSync(path.join(certificat, 'key.pem')),
  cert: fs.readFileSync(path.join(certificat, 'cert.pem'))}, serve) : http.createServer(serve);
let browser;
let currentPage;
const report = [];
function pass(test, data = {}) { report.push({test, platform: process.platform, browser: browser?.version(), channel: process.env.PWA_BROWSER_CHANNEL || "chromium", ...data}); console.log('OK', test, JSON.stringify(data)); }
async function boot(page, url) {
  await page.goto(url);
  await page.waitForFunction(() => !!window.pwaTest || !document.querySelector('#failure').hidden || /TypeError|PythonError|Error:/.test(document.querySelector('#status').textContent), null, {timeout: 120000});
  let status = await page.locator('#status').innerText();
  if (status.includes('déjà ouvert') && page.context().pages().every(other => other === page || !other.url().startsWith(new URL(url).origin + base))) {
    // CDP peut rendre close/goto avant la libération du verrou de l'ancien
    // document. Attendre la libération réelle ; ne masquer aucun second onglet.
    await page.waitForFunction(async () => !(await navigator.locks.query()).held.some(lock => lock.name.startsWith('petits-pas-pwa-prototype')), null, {timeout:5000});
    await page.goto(url);
    await page.waitForFunction(() => !!window.pwaTest || !document.querySelector('#failure').hidden, null, {timeout:120000});
    status = await page.locator('#status').innerText();
  }
  assert(await page.locator('#failure').isHidden(), await page.locator('#diagnostic').textContent());
  assert(!/Error/.test(status), status);
  await page.frameLocator('#app').locator('h1').waitFor({timeout: 60000});
  await page.locator('#tools').evaluate(node => {node.open = true;});
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
  await frame.locator('.bandeau .marque').waitFor({timeout: 30000});
  const result = frame.getByRole('button', {name: 'J’ai pris connaissance du résultat'});
  if (await result.count()) {
    await result.click();
    await frame.getByRole('heading', {name: "Gérer l'école", exact: true}).waitFor();
  }
}
(async () => {
  assert(JSON.parse(fs.readFileSync(path.join(root, 'config.json'))).testMode, 'Reconstruire avec --test');
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `${tls ? 'https' : 'http'}://127.0.0.1:${server.address().port}${base}`;
  browser = await playwright.chromium.launch({headless: true,
    ...(process.env.PWA_BROWSER_CHANNEL ? {channel: process.env.PWA_BROWSER_CHANNEL} : {}),
    ...(process.env.PWA_CHROMIUM ? {executablePath: process.env.PWA_CHROMIUM} : {}),
    // Certificat éphémère de ce seul serveur de test ; aucun réglage livré.
    args: ['--no-sandbox', '--disable-dev-shm-usage', ...(tls ? ['--ignore-certificate-errors'] : [])]});
  const context = await browser.newContext({acceptDownloads: true, ignoreHTTPSErrors: tls});
  let page = await context.newPage();
  currentPage = page;
  page.on('console', message => { if (message.type() === 'error' || message.type() === 'warning') console.error('CONSOLE', message.text()); });
  page.on('pageerror', error => console.error('PAGE', error.message));
  const started = performance.now();
  await boot(page, url);
  if (base !== '/') {
    const registrationScope = await page.evaluate(async () => (await navigator.serviceWorker.getRegistration()).scope);
    assert.equal(registrationScope, url);
    const outside = await context.newPage();
    await outside.goto(new URL('/petits-pas/temoin.html', url).href);
    assert.equal(await outside.evaluate(() => navigator.serviceWorker.controller), null);
    assert.equal(await outside.locator('h1').innerText(), 'Site Hugo fictif');
    await outside.close();
    pass('Portée du Service Worker limitée au sous-chemin, site Hugo accessible sans contrôle PWA');
  }
  pass('Django, migrations, pont SW/WSGI et installation', {coldMs: Math.round(performance.now() - started)});
  const manifest = await page.evaluate(async () => (await fetch('./manifest.webmanifest')).json());
  assert.equal(manifest.start_url, './'); assert.equal(manifest.scope, './');
  assert.deepEqual(manifest.icons.map(icon => icon.sizes), ['192x192', '512x512']);
  for (const icon of manifest.icons) assert.equal(await page.evaluate(async src => (await fetch(src)).status, icon.src), 200);
  await page.evaluate(() => {
    const event = new Event('beforeinstallprompt', {cancelable: true});
    event.prompt = async () => {window.installRequested = true;};
    event.userChoice = Promise.resolve({outcome: 'dismissed'});
    window.dispatchEvent(event);
  });
  await page.getByRole('button', {name: 'Installer Petits Pas', exact: true}).click();
  assert.equal(await page.evaluate(() => window.installRequested), true);
  await page.setViewportSize({width: 390, height: 844});
  await page.locator('#tools').evaluate(node => {node.open = false;});
  assert((await page.locator('#app').boundingBox()).height > 400);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.setViewportSize({width: 1280, height: 720});
  await page.locator('#tools').evaluate(node => {node.open = true;});
  const visibleConfig = JSON.parse(fs.readFileSync(path.join(serverRoot, 'config.json')));
  assert.equal(await page.locator('#version').innerText(), 'Version ' + (visibleConfig.application_version || visibleConfig.version));
  pass('Manifeste et icônes PNG, installation proposée ou refusée, coque mobile sans débordement et version visible');
  const unsupported = await browser.newContext();
  await unsupported.addInitScript(() => Object.defineProperty(navigator, 'locks', {value: undefined}));
  const refused = await unsupported.newPage(); await refused.goto(url);
  await refused.getByRole('heading', {name: 'Petits Pas n’a pas pu démarrer'}).waitFor();
  assert.match(await refused.locator('#failure-help').innerText(), /Chrome ou Edge/);
  assert.equal(await refused.locator('#app').isHidden(), true);
  await unsupported.close();
  pass('Navigateur sans Web Locks refusé avec aide et sans lancer Django');
  let frame = page.frameLocator('#app');
  const csrf = await frame.locator('[name="csrfmiddlewaretoken"]').inputValue();
  const refus = [{headers: [['Referer', url]], raison: 'jeton absent'}];
  if (tls) refus.push(
    {headers: [['X-CSRFToken', csrf]], raison: 'référent absent'},
    {headers: [['X-CSRFToken', csrf], ['Referer', 'https://autre-origine.example/']], raison: 'référent étranger'});
  for (const essai of refus) {
    const response = await page.evaluate(args => window.pwaTest({kind: 'http', request: {
      url: args.url + 'app/installation/', method: 'POST', headers: args.headers, body: ''}}), {url, headers: essai.headers});
    assert.equal(response.result.status, 403, essai.raison);
  }
  pass(tls ? 'HTTPS : jeton absent et référents absent ou étranger refusés par CSRF' : 'Jeton CSRF absent refusé');
  for (const [name, value] of Object.entries({ecole_nom: 'École fictive PWA', commune: 'Commune fictive', first_name: 'Nadia', last_name: 'Fictive', username: 'direction-fictive', password1: 'Test-fictif-PWA-2026!', password2: 'Test-fictif-PWA-2026!'})) {
    await frame.locator(`[name="${name}"]`).fill(value);
  }
  const demarrageCourt = !!(await frame.locator('[name="preparer_classe"]').count());
  if (demarrageCourt) {
    assert(await frame.locator('[name="preparer_classe"]').isChecked());
    await frame.locator('[name="annee_scolaire"]').fill('2026-2027');
    await frame.locator('[name="classe_nom"]').fill('Classe fictive');
  }
  await frame.getByRole('button', {name: /Créer (l’école et mon compte|et commencer)/}).click();
  await frame.getByRole('heading', {name: demarrageCourt ? /Ajouter/ : "Gérer l'école", exact: !demarrageCourt}).waitFor({timeout: 30000});
  if (demarrageCourt) {
    assert.equal(await python(page, "from suivi.models import Classe; Classe.objects.get().etat"), 'active');
    assert.equal(await python(page, "from comptes.models import AffectationClasse; AffectationClasse.objects.get().type"), 'responsable');
    assert.equal(await python(page, "from suivi.models import AdoptionReferentiel, ChoixEcoleAnnuel; AdoptionReferentiel.objects.get(courante=True).version_id == ChoixEcoleAnnuel.objects.get().version_proposee_id"), true);
  }
  pass('Formulaire installation, première classe si proposée, CSRF et session virtuelle');
  if (process.env.PWA_OLD_BUNDLE) {
    const oldHash = await python(page, `
import io, hashlib
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
buffer = io.BytesIO()
Image.new('RGB', (10, 12), (30, 80, 110)).save(buffer, 'PNG')
old_name = default_storage.save('ancienne-realisation-fictive.png', ContentFile(buffer.getvalue()))
hashlib.sha256(buffer.getvalue()).hexdigest()
`);
    serverRoot = root;
    const expected = JSON.parse(fs.readFileSync(path.join(root, 'config.json'))).version;
    await page.evaluate(async () => {const r=await navigator.serviceWorker.getRegistration(); await r.update();});
    await page.waitForFunction(async () => !!(await navigator.serviceWorker.getRegistration()).waiting, null, {timeout: 120000});
    let next;
    for (const sw of context.serviceWorkers()) {
      if ((await sw.evaluate(() => CACHE)).endsWith(expected)) next = sw;
    }
    assert(next, 'Nouveau Service Worker absent');
    const activated = next.evaluate(() => new Promise(resolve => self.addEventListener('activate', () => resolve(true), {once:true})));
    await page.close(); await activated;
    page = await context.newPage(); currentPage = page;
    await boot(page, url); await login(page); frame = page.frameLocator('#app');
    assert.equal(await python(page, "import os; os.environ['CARNET_VERSION']"), JSON.parse(fs.readFileSync(path.join(root, 'config.json'))).application_version || expected);
    assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
    assert.equal(await python(page, "from django.core.files.storage import default_storage; import hashlib; source = default_storage.open('ancienne-realisation-fictive.png', 'rb'); old_content = source.read(); source.close(); hashlib.sha256(old_content).hexdigest()"), oldHash);
    pass('Passage réel de l’ancien runtime au nouveau, connexion et base/média conservés');
  }

  assert.equal(await python(page, "import hashlib; hashlib.pbkdf2_hmac('sha256', b'password', b'salt', 1).hex()"), '120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b');
  assert.deepEqual(JSON.parse(await python(page, "import json; from PIL import Image; json.dumps(sorted(Image.ID))")), ['JPEG','PNG','WEBP']);
  const nativeKdf = execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', "import hashlib,json; print(json.dumps({name:hashlib.pbkdf2_hmac(name, 'mot-fictif-é'.encode(), b'sel-fictif', 123, 42).hex() for name in ('sha1','sha256','sha512')}))"], {encoding:'utf8'}).trim();
  assert.deepEqual(JSON.parse(await python(page, "json.dumps({name:hashlib.pbkdf2_hmac(name, 'mot-fictif-é'.encode(), b'sel-fictif', 123, 42).hex() for name in ('sha1','sha256','sha512')})")), JSON.parse(nativeKdf));
  assert.equal(await python(page, "hashlib.scrypt(b'password', salt=b'NaCl', n=16, r=1, p=1, dklen=32).hex()"), execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', "import hashlib; print(hashlib.scrypt(b'password', salt=b'NaCl', n=16, r=1, p=1, dklen=32).hex())"], {encoding:'utf8'}).trim());
  pass('PBKDF2 SHA-1/256/512 et scrypt compatibles natif, décodeurs privés');
  const initialMediaCount = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result.lazyMediaFiles;

  const ids = JSON.parse(await python(page, `
import json
from suivi.models import Ecole, Classe, Eleve, Scolarite, Competence
from comptes.models import Utilisateur, AppartenanceEcole, AffectationClasse
ecole = Ecole.objects.get()
classe, creee = Classe.objects.get_or_create(ecole=ecole, nom='Classe fictive', annee_scolaire='2026-2027')
appartenance = AppartenanceEcole.objects.get(utilisateur__username='direction-fictive')
if creee:
    AffectationClasse.objects.create(appartenance=appartenance, classe=classe, type='responsable')
    classe.activer()
eleve = Eleve.objects.create(ecole=ecole, prenom='Ana', nom='Fictive')
Scolarite.objects.create(eleve=eleve, classe=classe, annee_scolaire='2026-2027', niveau='MS')
competence = Competence.objects.filter(domaine__ecole=ecole).first()
json.dumps({'eleve': eleve.pk, 'competence': competence.pk, 'classe': classe.pk})
`));
  await page.locator('#app').evaluate((node, route) => {node.src = route;}, `${base}app/eleve/${ids.eleve}/`);
  const button = frame.locator(`#c${ids.competence} button.bascule`);
  await button.waitFor({timeout: 30000});
  await button.click();
  await page.waitForFunction(() => document.querySelector('#app').contentDocument.querySelector('button[data-statut="reussi"]'));
  assert.equal(await python(page, "from suivi.models import Observation; Observation.objects.get().statut"), 'reussi');
  pass('Saisie HTMX réelle et ORM');
  const forbidden = await page.evaluate(async ({route}) => {
    const response = await fetch(route, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'csrfmiddlewaretoken=invalide'});
    return response.status;
  }, {route: `${base}app/eleve/${ids.eleve}/competence/${ids.competence}/basculer/`});
  assert.equal(forbidden, 403);
  pass('CSRF invalide refusé');
  await page.locator('#app').evaluate((node, route) => {node.src = route;}, `${base}app/eleve/${ids.eleve}/competence/${ids.competence}/trace/`);
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
  assert(media.photo.endsWith('.jpg'), 'La photo normalisée doit être enregistrée en JPEG');
  const photoResponse = await page.evaluate(async route => {const r=await fetch(route);return {status:r.status,type:r.headers.get('content-type'),bytes:(await r.arrayBuffer()).byteLength};}, `${base}app/media/trace/${media.id}/`);
  assert.equal(photoResponse.status, 200); assert.equal(photoResponse.type, 'image/jpeg'); assert(photoResponse.bytes > 20);
  pass('Upload multipart, normalisation JPEG et média autorisé local');
  const pureRead = await page.evaluate(async route => window.pwaTest({kind:'http',
    request:{url:location.origin+route,method:'GET',headers:[],body:''}}), `${base}app/media/trace/${media.id}/`);
  assert.equal(pureRead.result.status, 200);
  assert.equal(pureRead.durability.changed, false);
  assert.equal(pureRead.durability.writtenBytes, 0);
  const sqlOnly = await page.evaluate(() => window.pwaTest({kind:'test-python',
    code:"from suivi.models import Ecole; Ecole.objects.update(commune='Commune fictive modifiée')"}));
  assert.equal(sqlOnly.durability.writtenFiles, 1, 'Une écriture SQL a recopié les médias');
  pass('Lecture du média sans écriture OPFS ; modification SQL sans recopie des médias');
  // Preuve ciblée #PWA11 : accès fichier Python/Pillow, puis écriture en place.
  await python(page, `
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
with default_storage.open(Trace.objects.get().photo.name, 'rb') as source:
    with Image.open(source) as image:
        image.load()
        assert image.width > 0
    source.seek(0)
    original_media = source.read()
proof_name = default_storage.save('preuve-pwa11-fictive.png', ContentFile(original_media))
`);
  let lazyMetrics = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  assert.equal(lazyMetrics.residentMediaBytes, 0);
  assert.equal(lazyMetrics.lazyMediaFiles, initialMediaCount + 2);
  await python(page, `
with default_storage.open(proof_name, 'r+b') as cible:
    cible.seek(0, 2)
    cible.write(b'PWA11-fictif')
with default_storage.open(proof_name, 'rb') as cible:
    assert cible.read() == original_media + b'PWA11-fictif'
`);
  lazyMetrics = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  assert.equal(lazyMetrics.residentMediaBytes, 0);
  assert(lazyMetrics.mediaMaterializedBytes > 0);
  await python(page, `
from pathlib import Path
p = Path('/data/media') / proof_name
p.write_bytes(original_media)  # O_TRUNC sans recopier l'ancien fichier
with p.open('ab') as cible:
    cible.write(b'append-fictif')
q = p.with_name('preuve-renommee-fictive.png')
p.rename(q)
assert q.read_bytes() == original_media + b'append-fictif'
q.unlink()
assert not p.exists() and not q.exists()
`);
  lazyMetrics = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  assert.equal(lazyMetrics.residentMediaBytes, 0);
  assert.equal(lazyMetrics.lazyMediaFiles, initialMediaCount + 1);
  pass('PWA11 : Pillow sur File OPFS, création, modification, troncature, ajout, renommage et suppression sans médias résidents');
  await page.getByRole('button', {name: 'Sauvegardes / transfert'}).click();
  await page.frameLocator('#app').getByRole('heading', {name: 'Sauvegardes locales', exact: true}).waitFor();
  const downloadReady = page.waitForEvent('download');
  await page.frameLocator('#app').getByRole('button', {name: 'Télécharger une sauvegarde', exact: true}).click();
  const download = await downloadReady;
  const archivePath = await download.path();
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', "import sys,zipfile,json,hashlib; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read('manifest.json')); assert m['format']=='petits-pas-paquet'; assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in m['files'].items()); assert any(n.startswith('media/') for n in m['files'])", archivePath]);
  pass('Export ZIP commun au mode autonome, manifeste et photos vérifiés');
  await page.frames()[1].goto(url + 'app/verifier-zip/');
  await frame.locator('[name="archive"]').setInputFiles(archivePath);
  await frame.getByRole('button', {name: 'Vérifier le ZIP pour ouvrir une copie', exact: true}).click();
  await frame.getByRole('heading', {name: 'La copie est prête', exact: true}).waitFor();
  assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
  await frame.getByRole('button', {name: 'Ouvrir la copie pour vérifier', exact: true}).click();
  await page.waitForURL(url + '?apercu=oui', {timeout: 60000});
  await page.waitForFunction(() => !!window.pwaTest, null, {timeout: 120000});
  frame = page.frameLocator('#app');
  await frame.locator('[name="nom_utilisateur"]').waitFor();
  await login(page);
  assert.equal(await python(page, 'from django.conf import settings; settings.ESPACE_APERCU'), true);
  assert.equal(await python(page, 'from django.conf import settings; settings.ESPACE_ESSAI'), false);
  await python(page, "from suivi.models import Ecole; Ecole.objects.update(nom='Copie fictive vérifiée')");
  await page.locator('#backup').click();
  await frame.getByRole('heading', {name: 'Sauvegardes locales', exact: true}).waitFor();
  assert.equal(await frame.getByRole('heading', {name: 'Restaurer une sauvegarde', exact: true}).count(), 0);
  const previewDownload = await Promise.all([page.waitForEvent('download'), frame.getByRole('button', {name:'Télécharger une sauvegarde',exact:true}).click()]);
  const previewPath = await previewDownload[0].path();
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
import sys,sqlite3,tempfile,zipfile
from contextlib import closing
with tempfile.TemporaryDirectory() as folder:
    with zipfile.ZipFile(sys.argv[1]) as archive: archive.extract('carnet.sqlite3',folder)
    with closing(sqlite3.connect(folder+'/carnet.sqlite3')) as db, db:
        assert db.execute('SELECT nom FROM suivi_ecole').fetchone()[0]=='Copie fictive vérifiée'
`, previewPath]);
  const premiereInstallation = await browser.newContext({acceptDownloads: true, ignoreHTTPSErrors: tls});
  const appareilVide = await premiereInstallation.newPage();
  await boot(appareilVide, url);
  await appareilVide.frames()[1].goto(url + 'app/verifier-zip/');
  const vierge = appareilVide.frameLocator('#app');
  await vierge.locator('[name="archive"]').setInputFiles(previewPath);
  await vierge.getByRole('button', {name: 'Vérifier le ZIP pour ouvrir une copie', exact:true}).click();
  await vierge.getByRole('button', {name: 'Utiliser ce ZIP comme école sur cet appareil', exact:true}).click();
  await vierge.locator('[name="nom_utilisateur"]').waitFor();
  await login(appareilVide);
  assert.equal(await python(appareilVide, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'Copie fictive vérifiée');
  assert.equal(await python(appareilVide, 'from django.conf import settings; settings.ESPACE_APERCU'), false);
  await premiereInstallation.close();
  pass('Installation explicite du ZIP vérifié sur un appareil vide, sans école provisoire');
  // ZIP issu de la projection serveur réelle, pas d'une sauvegarde locale.
  const exportFixture = fs.mkdtempSync(path.join(os.tmpdir(), 'petits-pas-export-fictif-'));
  const exportZip = path.join(exportFixture, 'ecole.zip');
  try {
    execFileSync(process.env.PWA_PYTHON || 'python3',
      [path.join(__dirname, 'qualifier-export-ecole.py'), '--destination', exportZip], {stdio:'pipe'});
    const imported = await browser.newContext({acceptDownloads:true, ignoreHTTPSErrors:tls});
    try {
      const copied = await imported.newPage();
      await boot(copied, url);
      await copied.frames()[1].goto(url + 'app/verifier-zip/');
      const school = copied.frameLocator('#app');
      await school.locator('[name="archive"]').setInputFiles(exportZip);
      await school.getByRole('button', {name:'Vérifier le ZIP pour ouvrir une copie', exact:true}).click();
      await school.getByRole('button', {name:'Utiliser ce ZIP comme école sur cet appareil', exact:true}).click();
      await school.locator('[name="nom_utilisateur"]').fill('export-fictif');
      await school.locator('[name="mot_de_passe"]').fill('Copie!Fictive2026');
      await school.getByRole('button', {name:'Entrer', exact:true}).click();
      await school.locator('.bandeau .marque').waitFor({timeout:30000});
      assert.equal(await python(copied, 'from suivi.models import Ecole; Ecole.objects.get().nom'), 'École fictive export');
      assert.equal(await python(copied, 'from comptes.models import Utilisateur; Utilisateur.objects.get().check_password("Service!Fictif2026")'), false);
      assert.equal(await python(copied, 'from suivi.models import Trace; Trace.objects.count() > 0'), true);
      assert.equal(await python(copied, 'from suivi.models import ExportEcole; ExportEcole.objects.count()'), 0);
      const media = await python(copied, 'from suivi.models import Trace; Trace.objects.first().photo.name');
      assert.equal(await python(copied, `from django.core.files.storage import default_storage; default_storage.exists(${JSON.stringify(media)})`), true);
      pass('Export serveur installé dans la PWA : mot de passe local, école, traces et média conservés');
    } finally {await imported.close();}
  } finally {fs.rmSync(exportFixture, {recursive:true, force:true});}
  await page.close(); page = await context.newPage(); currentPage = page;
  await boot(page, url + '?apercu=oui'); await login(page);
  assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'Copie fictive vérifiée');
  assert.equal(await page.locator('#changer-espace').getAttribute('href'), base);
  await page.close(); page = await context.newPage(); currentPage = page;
  await boot(page, url); await login(page); frame = page.frameLocator('#app');
  assert.equal(await python(page, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
  assert(await page.locator('#reprendre-apercu').isVisible());
  await page.frames()[1].goto(url + 'app/gestion/sauvegardes-locales/');
  pass('ZIP ouvert dans une copie distincte, nouvelle connexion, modifications/export persistants et retour sans remplacer l’école habituelle');
  await page.frames()[1].goto(url + 'app/gestion/sauvegardes-locales/');
  await frame.getByText(/Dernier ZIP préparé sur cet appareil/).waitFor();
  await boot(page, url); await login(page);
  await python(page, "from suivi.models import Ecole, Trace");
  await page.getByRole('button', {name: 'Sauvegardes / transfert'}).click();
  await frame.getByText(/Dernier ZIP préparé sur cet appareil/).waitFor();
  assert.equal(await python(page, "from suivi.paquet_local import suivi_export; suivi_export(__import__('pathlib').Path('/data'))['rappel_sauvegarde_local']"), false);
  pass('Date du ZIP préparé affichée, rappel commun levé sans prétendre confirmer son enregistrement');
  const transfer = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'petits-pas-transfert-'));
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
from pathlib import Path
import sqlite3, sys
from contextlib import closing
from suivi.paquet_local import preparer_restauration, appliquer_restauration, creer_sauvegarde
parent = Path(sys.argv[2]); paquet = parent / 'paquet-autonome'; paquet.mkdir()
with open(sys.argv[1], 'rb') as source:
    preparation = preparer_restauration(source, parent, paquet.name)
appliquer_restauration(paquet, preparation)
with closing(sqlite3.connect(paquet/'carnet.sqlite3')) as db, db:
    assert db.execute('SELECT commentaire FROM suivi_trace').fetchone()[0] == 'Réalisation entièrement fictive.'
    db.execute("UPDATE suivi_ecole SET nom='École fictive transférée'")
with (parent/'depuis-local.zip').open('wb') as sortie: creer_sauvegarde(paquet, sortie)
with closing(sqlite3.connect(paquet/'carnet.sqlite3')) as db, db:
    db.execute("INSERT INTO django_migrations(app,name,applied) VALUES ('suivi','9999_inconnue','2026-10-02')")
with (parent/'version-future.zip').open('wb') as sortie: creer_sauvegarde(paquet, sortie)
`, archivePath, transfer]);
  pass('ZIP PWA restauré dans un paquet autonome natif puis réexporté');
  async function prepareImport(file) {
    await page.frames()[1].goto(url + 'app/gestion/sauvegardes-locales/');
    await frame.locator('[name="archive"]').setInputFiles(file);
    await frame.getByRole('button', {name: 'Vérifier la sauvegarde', exact: true}).click();
  }
  await prepareImport(path.join(transfer, 'version-future.zip'));
  await frame.getByText(/Cette sauvegarde provient d'une version plus récente/).waitFor();
  assert.equal(await python(page, "Ecole.objects.get().nom"), 'École fictive PWA');
  pass('Version de base inconnue refusée avant confirmation, école actuelle conservée');
  await prepareImport(path.join(transfer, 'depuis-local.zip'));
  await frame.getByRole('heading', {name: 'Confirmer la restauration'}).waitFor();
  await frame.getByRole('button', {name: 'Annuler', exact: true}).click();
  await frame.getByRole('heading', {name: 'Restaurer une sauvegarde'}).waitFor();
  assert.equal(await python(page, "Ecole.objects.get().nom"), 'École fictive PWA');
  pass('Vérification et annulation sans remplacer les données');
  await prepareImport(path.join(transfer, 'depuis-local.zip'));
  await frame.getByRole('button', {name: 'Confirmer la restauration', exact: true}).click();
  await frame.locator('[name="nom_utilisateur"]').waitFor(); await login(page);
  assert.equal(await python(page, "Ecole.objects.get().nom"), 'École fictive transférée');
  assert.equal(await python(page, "Trace.objects.get().photo.name"), media.photo);
  assert.equal(await python(page, "from pathlib import Path; len(list(Path('/').glob('.data-avant-restauration-*')))"), 0);
  pass('Restauration du ZIP autonome dans la PWA, photo conservée et ancienne copie mémoire libérée');
  // Le retour vers la sauvegarde initiale utilise le même parcours enseignant.
  await prepareImport(archivePath);
  await frame.getByRole('button', {name: 'Confirmer la restauration', exact: true}).click();
  await frame.locator('[name="nom_utilisateur"]').waitFor(); await login(page);
  assert.equal(await python(page, "Ecole.objects.get().nom"), 'École fictive PWA');
  const recoveryDownload = page.waitForEvent('download', {timeout: 120000});
  await page.getByRole('button', {name: 'Exporter l’état de récupération'}).click();
  const recovery = await recoveryDownload;
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
import sys,sqlite3,tempfile,zipfile
from contextlib import closing
from pathlib import Path
from suivi.paquet_local import preparer_restauration
with tempfile.TemporaryDirectory() as dossier:
    with open(sys.argv[1],'rb') as source: p=preparer_restauration(source,Path(dossier))
    with closing(sqlite3.connect(p.etape/'carnet.sqlite3')) as db, db:
        assert db.execute('SELECT nom FROM suivi_ecole').fetchone()[0]=='École fictive transférée'
`, await recovery.path()]);
  pass('État avant remplacement exportable et compatible avec le paquet autonome');
  const printPage = await context.newPage();
  await printPage.goto(url + `app/eleve/${ids.eleve}/carnet.pdf?colonnes=2&contenu=observes`);
  await printPage.getByRole('button', {name: 'Imprimer / enregistrer en PDF', exact: true}).waitFor();
  await printPage.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  assert(await printPage.locator('img').count() > 0);
  await printPage.evaluate(() => {window.print = () => window.printCalled = true;});
  await printPage.getByRole('button', {name: 'Imprimer / enregistrer en PDF', exact: true}).click();
  assert(await printPage.evaluate(() => window.printCalled));
  const pdf = await printPage.pdf({preferCSSPageSize: true, printBackground: true});
  const pdfPath = path.join(transfer, 'carnet.pdf'); fs.writeFileSync(pdfPath, pdf);
  const text = process.env.PWA_PDF_PYTHON === 'oui'
    ? execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', "from pypdf import PdfReader; import sys; print('\\n'.join(p.extract_text() for p in PdfReader(sys.argv[1]).pages))", pdfPath], {encoding: 'utf8'})
    : execFileSync('pdftotext', [pdfPath, '-'], {encoding: 'utf8'});
  assert(text.includes('Ana')); assert(text.includes('Réalisation entièrement fictive.'));
  assert(!text.includes('Le carnet est prêt à imprimer'));
  await printPage.close();
  const grid = await context.newPage();
  await grid.goto(url + `app/classe/${ids.classe}/competence/${ids.competence}/grille.pdf`);
  await grid.getByRole('button', {name: 'Imprimer / enregistrer en PDF', exact: true}).waitFor();
  assert((await grid.locator('tbody').innerText()).includes('Ana'));
  await grid.close();
  pass('Carnet PDF Chromium avec photo et texte, grille imprimable, bouton impression');
  await page.frames()[1].goto(url + `app/classe/${ids.classe}/edition/`);
  await frame.locator(`input[name="eleves"][value="${ids.eleve}"]`).check();
  await frame.getByRole('button', {name: 'Préparer l’impression des carnets', exact: true}).click();
  await frame.getByRole('heading', {name: 'Carnets à imprimer', exact: true}).waitFor();
  assert.equal(await frame.locator('article.carnet').count(), 1);
  assert((await frame.locator('article.carnet').innerText()).includes('Ana'));
  pass('Préparation groupée par les mêmes choix, document imprimable unique sans moteur natif');

  await python(page, "from comptes.models import ResponsabiliteEcole, AffectationClasse; ResponsabiliteEcole.objects.update(etat='suspendue'); AffectationClasse.objects.update(type='contributeur')");
  const denied = await page.evaluate(async route => {
    const responses = await Promise.all([route, route.split('/app/')[0] + '/app/pwa/autoriser-recuperation/', route.split('/app/')[0] + '/app/gestion/sauvegardes-locales/'].map(url => fetch(url)));
    return responses.map(r => r.status);
  }, `${base}app/eleve/${ids.eleve}/carnet.pdf`);
  assert([403,404].includes(denied[0])); assert.equal(denied[1], 403); assert.equal(denied[2], 403);
  await python(page, "AffectationClasse.objects.update(etat='suspendue')");
  const deniedMedia = await page.evaluate(async route => window.pwaTest({kind:'http',
    request:{url:location.origin+route,method:'GET',headers:[],body:''}}), `${base}app/media/trace/${media.id}/`);
  assert([403,404].includes(deniedMedia.result.status));
  await python(page, "ResponsabiliteEcole.objects.update(etat='active'); AffectationClasse.objects.update(type='responsable',etat='active')");
  pass('Contributeur sans direction : impression du carnet et exports réservés refusés');



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
  assert.equal(await python(page, "import sqlite3; db=sqlite3.connect('/data/carnet.sqlite3'); checks=str((db.execute('PRAGMA quick_check').fetchone(), db.execute('PRAGMA foreign_key_check').fetchall())); db.close(); checks"), "(('ok',), [])");
  pass('Quota simulé et intégrité SQLite après reprise');
  await page.close();
  const reopened = await context.newPage(); currentPage = reopened;
  await boot(reopened, url);
  assert.equal(await python(reopened, "from suivi.models import Trace; Trace.objects.get().photo.name"), media.photo);
  pass('Fermeture de la page propriétaire puis réouverture hors ligne');
  await context.setOffline(false);
  const config = JSON.parse(fs.readFileSync(path.join(root, 'config.json')));
  const previousVersion = config.version;
  const sw = fs.readFileSync(path.join(root, 'sw.js'), 'utf8').replace(config.version, config.version + '-mise-a-jour-fictive');
  config.version += '-mise-a-jour-fictive';
  config.assets.find(asset => asset.url === '/sw.js').sha256 = require('node:crypto').createHash('sha256').update(sw).digest('hex');

  const migratedApplication = path.join(transfer, 'application-migration-fictive.zip');
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as original, zipfile.ZipFile(sys.argv[2],'w',zipfile.ZIP_DEFLATED) as target:
    for name in original.namelist(): target.writestr(name,original.read(name))
    last=sorted(n for n in original.namelist() if n.startswith('suivi/migrations/00') and n.endswith('.py'))[-1].split('/')[-1][:-3]
    sql = "CREATE TABLE pwa_test_upgrade (preuve TEXT); INSERT INTO pwa_test_upgrade VALUES ('migration fictive');"
    code = "from django.db import migrations\\nclass Migration(migrations.Migration):\\n    dependencies = [('suivi', " + repr(last) + ")]\\n    operations = [migrations.RunSQL(" + repr(sql) + ")]\\n"
    target.writestr('suivi/migrations/0026_pwa_test.py', code)
`, path.join(root, 'application.zip'), migratedApplication]);
  const application = fs.readFileSync(migratedApplication);
  config.assets.find(asset => asset.url === '/application.zip').sha256 = require('node:crypto').createHash('sha256').update(application).digest('hex');
  published = {config, sw, application};
  await reopened.getByRole('button', {name: 'Vérifier les mises à jour', exact: true}).click();
  await reopened.locator('#update').waitFor({state: 'visible', timeout: 120000});
  // Le runtime actif continue à lire l'école pendant le téléchargement.
  assert.equal(await python(reopened, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'École fictive PWA');
  const navigated = reopened.waitForEvent('framenavigated', {predicate: f => f === reopened.mainFrame(), timeout: 120000});
  await reopened.locator('#update').click(); await navigated;
  await reopened.waitForFunction(() => !!window.pwaTest, null, {timeout: 120000});
  await reopened.frameLocator('#app').locator('h1').waitFor();
  assert.equal(await python(reopened, "from suivi.models import Trace; Trace.objects.get().photo.name"), media.photo);
  assert.equal(await python(reopened, "import os; os.environ['CARNET_VERSION']"), config.application_version || config.version);
  const preserved = await reopened.evaluate(() => new Promise((resolve, reject) => {
    const request = indexedDB.open('petits-pas-pwa-prototype-v1' + (location.pathname === '/' ? '' : '-' + encodeURIComponent(location.pathname)));
    request.onsuccess = () => {const db=request.result; const get=db.transaction('state').objectStore('state').get('active'); get.onsuccess=()=>{resolve(get.result.recovery.version); db.close();}; get.onerror=()=>reject(get.error);};
  }));
  assert.equal(preserved, previousVersion);
  assert.equal(await python(reopened, "from django.db import connection; connection.cursor().execute('SELECT preuve FROM pwa_test_upgrade').fetchone()[0]"), 'migration fictive');
  pass('Mise à jour explicite, ancien runtime arrêté, migration SQL appliquée, école conservée et checkpoint pré-version retenu');
  await python(reopened, "from django.db import connection; connection.cursor().execute(\"INSERT INTO django_migrations(app,name,applied) VALUES ('suivi','9999_inconnue','2026-10-02')\")");
  await assert.rejects(boot(reopened, url));
  const rescueDownload = reopened.waitForEvent('download', {timeout: 120000});
  await reopened.getByRole('button', {name: 'Exporter l’état de récupération'}).click();
  const rescued = await rescueDownload;
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
import sys,tempfile,sqlite3
from contextlib import closing
from pathlib import Path
from suivi.paquet_local import preparer_restauration
with tempfile.TemporaryDirectory() as dossier:
    with open(sys.argv[1],'rb') as source: p=preparer_restauration(source,Path(dossier))
    with closing(sqlite3.connect(p.etape/'carnet.sqlite3')) as db, db:
        assert db.execute('SELECT nom FROM suivi_ecole').fetchone()[0]=='École fictive PWA'
        assert not db.execute("SELECT 1 FROM django_migrations WHERE name='9999_inconnue'").fetchone()
`, await rescued.path()]);
  pass('Base incompatible refusée au démarrage sans création vide, récupération disponible sans connexion');

  // Le même navigateur possède deux écoles distinctes ; revenir ne restaure aucun ZIP.
  await reopened.close();
  let espace = await context.newPage(); currentPage = espace;
  await boot(espace, url + '?essai=oui');
  assert.equal(await python(espace, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'Ma Belle École');
  assert.equal(await python(espace, "from django.conf import settings; settings.ESPACE_ESSAI"), true);
  await python(espace, "from suivi.models import Ecole; Ecole.objects.update(nom='Essai modifié fictif')");
  await espace.close();
  espace = await context.newPage(); currentPage = espace;
  await boot(espace, url + '?essai=oui');
  assert.equal(await python(espace, "from suivi.models import Ecole; Ecole.objects.get().nom"), 'Essai modifié fictif');
  // Même échéance que la coque, accélérée pour exercer son arrêt réel.
  const uncertain = await espace.evaluate(async () => {
    const original = window.setTimeout;
    window.setTimeout = (callback, delay, ...args) => original(callback, delay === 900000 ? 5000 : delay, ...args);
    try {
      await window.pwaTest({kind:'test-python', code:"from suivi.models import Ecole; Ecole.objects.update(commune='Modification non activée fictive')", failpoint:'pause-before-activate'});
      return 'réponse inattendue';
    } catch (error) {return String(error.message);}
    finally {window.setTimeout = original;}
  });
  assert.match(uncertain, /Résultat incertain/);
  assert(await espace.locator('#app').isHidden());
  assert(await espace.locator('#failure').isVisible());
  await boot(espace, url + '?essai=oui');
  assert.notEqual(await python(espace, "from suivi.models import Ecole; Ecole.objects.get().commune"), 'Modification non activée fictive');
  pass('Expiration réelle de la coque : arrêt du Worker, réouverture du dernier état confirmé');
  const retour = await espace.locator('#changer-espace').getAttribute('href');
  assert.equal(retour, base);
  await espace.close();
  espace = await context.newPage(); currentPage = espace;
  // L'espace habituel avait été volontairement rendu incompatible par le test précédent.
  await espace.goto(url);
  await espace.getByRole('heading', {name: 'Petits Pas n’a pas pu démarrer'}).waitFor({timeout:120000});
  const archiveHabituelle = await Promise.all([espace.waitForEvent('download'), espace.locator('#recovery').click()]);
  const cheminHabituel = await archiveHabituelle[0].path();
  execFileSync(process.env.PWA_PYTHON || 'python3', ['-c', `
import sys,sqlite3,tempfile,zipfile
from contextlib import closing
with tempfile.TemporaryDirectory() as folder:
    with zipfile.ZipFile(sys.argv[1]) as archive: archive.extract('carnet.sqlite3',folder)
    with closing(sqlite3.connect(folder+'/carnet.sqlite3')) as db, db:
        assert db.execute('SELECT nom FROM suivi_ecole').fetchone()[0]=='École fictive PWA'
`, cheminHabituel]);
  pass('École fictive isolée, essais persistants et récupération de l’école habituelle indépendante');

  assert(!network.some(route => route.startsWith('/app/') || route.startsWith(base + 'app/')), 'Une requête métier est sortie vers le serveur statique');
  pass('Aucune requête métier sur le réseau');
  fs.writeFileSync(path.join(root, 'resultats-tests.json'), JSON.stringify(report, null, 2));
})().catch(async error => {
  console.error(error);
  if (currentPage) {
    console.error('STATUS', await currentPage.locator('#status').innerText());
    console.error('DIAGNOSTIC', await currentPage.locator('#diagnostic').textContent());
    for (const frame of currentPage.frames()) console.error('FRAME', frame.url(), (await frame.locator('body').innerText().catch(() => '')).slice(0, 4000));
  }
  process.exitCode = 1;
}).finally(async () => {
  if(browser) await browser.close(); server.close();
  if(certificat) fs.rmSync(certificat, {recursive: true, force: true});
});
