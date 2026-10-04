#!/usr/bin/env node
// Volumes fictifs, profils persistants dédiés et SIGKILL du seul navigateur lancé ici.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const {createRequire} = require('node:module');
const localRequire = createRequire(path.resolve(__dirname, '../pwa/package.json'));
const {chromium} = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')) : localRequire('playwright');
const root = path.resolve(__dirname, '../dist/pwa');
const output = path.resolve(__dirname, '../dist/qualification-pwa.json');
const config = JSON.parse(fs.readFileSync(path.join(root, 'config.json')));
assert(config.testMode, 'Construire avec --test ; les injections restent interdites en distribution.');
assert.equal(process.platform, 'linux', 'Qualification SIGKILL réservée à Linux.');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'petits-pas-qualification-'));
const requests = [];
const mime = {'.js':'text/javascript', '.mjs':'text/javascript', '.wasm':'application/wasm', '.html':'text/html', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml'};
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname; requests.push(pathname);
  const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(root + path.sep)) {res.writeHead(403).end(); return;}
  try {res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(fs.readFileSync(file));}
  catch {res.writeHead(404).end();}
});
let processBrowser, browser, context, page, url;
const report = {bundle: config.version, date: new Date().toISOString(),
  platform: `${os.platform()} ${os.arch()}`, samples: [], checks: []};
function pass(check) {report.checks.push(check); console.log('OK', check);}
async function boot() {
  const started = performance.now();
  processBrowser = spawn(process.env.PWA_CHROMIUM || chromium.executablePath(), [
    '--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--no-first-run',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
  ], {detached: true, stdio: ['ignore', 'ignore', 'pipe']});
  const endpoint = await new Promise((resolve, reject) => {
    let stderr = '';
    const timer = setTimeout(() => reject(new Error('Chromium ne démarre pas : ' + stderr.slice(-1000))), 30000);
    processBrowser.once('error', error => {clearTimeout(timer); reject(error);});
    processBrowser.stderr.on('data', bytes => {stderr += bytes; const match = stderr.match(/DevTools listening on (ws:\/\/\S+)/); if (match) {clearTimeout(timer); resolve(match[1]);}});
  });
  browser = await chromium.connectOverCDP(endpoint);
  context = browser.contexts()[0]; page = await context.newPage();
  await page.goto(url);
  await page.waitForFunction(() => !!window.pwaTest || /Error:/.test(document.querySelector('#status').textContent), null, {timeout: 120000});
  assert(await page.evaluate(() => !!window.pwaTest), await page.locator('#status').innerText());
  await page.frameLocator('#app').locator('h1').waitFor();
  return performance.now() - started;
}
function killBrowser() {
  if (processBrowser) {try {process.kill(-processBrowser.pid, 'SIGKILL');} catch (error) {if (error.code !== 'ESRCH') throw error;}}
}
async function rpc(code, failpoint = '') {
  return page.evaluate(args => window.pwaTest({kind:'test-python', ...args}), {code, failpoint});
}
async function value(code) {return (await rpc(code)).result;}
function browserPss() {
  const parents = new Map();
  for (const entry of fs.readdirSync('/proc').filter(name => /^\d+$/.test(name))) {
    try {const stat = fs.readFileSync(`/proc/${entry}/stat`, 'utf8'); parents.set(Number(entry), Number(stat.slice(stat.lastIndexOf(')') + 2).split(' ')[1]));} catch {}
  }
  const children = new Set([processBrowser.pid]);
  for (let previous = -1; previous !== children.size;) {previous = children.size; for (const [pid, parent] of parents) if (children.has(parent)) children.add(pid);}
  let bytes = 0;
  for (const pid of children) {try {const match = fs.readFileSync(`/proc/${pid}/smaps_rollup`, 'utf8').match(/^Pss:\s+(\d+) kB/m); if (match) bytes += Number(match[1]) * 1024;} catch {}}
  return bytes || null;
}
async function sample(photos, mutation) {
  const reads = [];
  for (let i = 0; i < 5; i++) {
    reads.push(await page.evaluate(async () => {
      const start = performance.now();
      const response = await window.pwaTest({kind:'http', request:{url:location.origin+'/app/eleve/1/', method:'GET', headers:[], body:''}});
      if (response.result.status !== 200) throw new Error('Lecture refusée');
      return {totalMs:performance.now()-start, ...response.durability};
    }));
  }
  const metrics = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  const storage = await page.evaluate(() => navigator.storage.estimate());
  const sorted = reads.map(r => r.totalMs).sort((a,b)=>a-b);
  const row = {photos, ...metrics, medianReadMs: sorted[2], maxReadMs: sorted[4],
    medianInventoryMs: reads.map(r=>r.snapshotMs).sort((a,b)=>a-b)[2],
    readWrittenBytes: reads.map(r=>r.writtenBytes),
    stateBytes: reads[4].bytes, mutationPersistMs: mutation?.durability.persistMs || null,
    browserPssBytes: browserPss(), originUsageBytes:storage.usage, originQuotaBytes:storage.quota};
  assert(reads.every(r => !r.changed && r.writtenBytes === 0), 'Une lecture pure a réécrit OPFS');
  report.samples.push(row); console.log('MESURE', JSON.stringify(row));
}
async function integrity(photos, name) {
  const hashes = JSON.parse(await value("import hashlib, json; from suivi.models import Trace; json.dumps(sorted({hashlib.sha256(trace.photo.read()).hexdigest() for trace in Trace.objects.all()}))"));
  assert.deepEqual(hashes, report.photoHashes, 'Photos perdues ou altérées après reprise');
  assert.equal(await value("from suivi.models import Trace; Trace.objects.count()"), photos);
  assert.equal(await value("from suivi.models import Ecole; Ecole.objects.get().nom"), name);
  assert.equal(await value("import sqlite3; db=sqlite3.connect('/data/carnet.sqlite3'); str((db.execute('PRAGMA quick_check').fetchone(), db.execute('PRAGMA foreign_key_check').fetchall()))"), "(('ok',), [])");
}
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  url = `http://127.0.0.1:${server.address().port}/`;
  report.coldMs = await boot(); report.browser = browser.version();
  const frame = page.frameLocator('#app');
  for (const [name, text] of Object.entries({ecole_nom:'École fictive qualification', commune:'Commune fictive', first_name:'Nadia', last_name:'Fictive', username:'direction-fictive', password1:'Test-fictif-PWA-2026!', password2:'Test-fictif-PWA-2026!'})) await frame.locator(`[name="${name}"]`).fill(text);
  // Garder le banc sur son école sans classe ; compatible avec les anciens bundles.
  if (await frame.locator('[name="preparer_classe"]').count()) {
    await frame.locator('[name="preparer_classe"]').uncheck();
    await frame.locator('[name="annee_scolaire"]').fill('2026-2027');
  }
  await frame.getByRole('button', {name: /Créer (l’école et mon compte|et commencer)/}).click();
  await frame.getByRole('heading', {name:"Gérer l'école", exact:true}).waitFor();
  await rpc(`
import io, random
from PIL import Image
from django.core.files.base import ContentFile
from suivi.models import Ecole, Classe, Eleve, Scolarite, Competence, Observation, Trace
from comptes.models import AppartenanceEcole, AffectationClasse
ecole=Ecole.objects.get()
appartenance=AppartenanceEcole.objects.get()
competence=Competence.objects.filter(domaine__ecole=ecole).first()
scolarites=[]
for c in range(6):
    classe=Classe.objects.create(ecole=ecole,nom=f'Classe fictive {c+1}',annee_scolaire='2026-2027')
    AffectationClasse.objects.create(appartenance=appartenance,classe=classe,type='responsable')
    classe.activer()
    for p in range(20):
        eleve=Eleve.objects.create(ecole=ecole,prenom=f'Enfant fictif {c*20+p+1}',nom='Fictif')
        scolarites.append(Scolarite.objects.create(eleve=eleve,classe=classe,annee_scolaire='2026-2027',niveau='MS'))
image=Image.frombytes('RGB',(512,384),random.Random(20261004).randbytes(512*384*3))
output=io.BytesIO(); image.save(output,format='JPEG',quality=70)
photo=output.getvalue()
def ajouter_photos(total):
    for i in range(Trace.objects.count(),total):
        scolarite=scolarites[i%120]
        observation,_=Observation.objects.get_or_create(eleve=scolarite.eleve,competence=competence)
        trace=Trace.objects.create(observation=observation,scolarite=scolarite,commentaire='Réalisation entièrement fictive.')
        trace.photo.save(f'qualification-{i}.jpg',ContentFile(photo + str(i).encode()))
`);
  report.jpegSha256 = await value("import hashlib; hashlib.sha256(photo).hexdigest()");
  pass('École fictive : 120 élèves, six classes, photographie synthétique reproductible');
  await sample(0);
  for (const count of [30,90,140,300,550]) {const mutation=await rpc(`ajouter_photos(${count})`); await sample(count,mutation);}
  report.photoHashes = JSON.parse(await value("import hashlib, json; json.dumps(sorted({hashlib.sha256(trace.photo.read()).hexdigest() for trace in Trace.objects.all()}))"));
  assert.equal(report.photoHashes.length, 550);
  assert.equal(await page.evaluate(async () => (await fetch('/app/eleve/1/')).status), 200);
  await page.locator('#volume').filter({hasText: 'Limite proche'}).waitFor();
  pass('Volume confirmé et avertissement visibles à proximité de la limite');
  await page.frames()[1].goto(url + 'app/gestion/sauvegardes-locales/');
  const downloadReady = page.waitForEvent('download', {timeout:120000});
  await frame.getByRole('button', {name:'Télécharger une sauvegarde',exact:true}).click();
  const download = await downloadReady;
  const archive = await download.path();
  report.exportBytes = fs.statSync(archive).size;
  execFileSync('python3',['-c',`
import sys,tempfile
from pathlib import Path
from suivi.paquet_local import preparer_restauration
with tempfile.TemporaryDirectory() as folder:
    with open(sys.argv[1],'rb') as source:
        prepared=preparer_restauration(source,Path(folder),taille_max=64*1024**2,fichiers_max=5000)
    assert prepared.nombre_medias==550
`,archive]);
  // Réimportation réelle : le multipart >20 Mio traverse bien le Service Worker.
  // Chromium et le script sont locaux ; CDP sait ouvrir ce chemin directement.
  // Playwright connectOverCDP limite sinon les transferts distants à 50 Mo.
  const upload = await context.newCDPSession(page);
  await upload.send('DOM.enable');
  const nodes = await upload.send('DOM.getFlattenedDocument', {depth:-1,pierce:true});
  const input = nodes.nodes.find(node => node.nodeName === 'INPUT'
    && node.attributes?.some((attribute,index) => attribute === 'name' && node.attributes[index+1] === 'archive'));
  assert(input, 'Champ de sauvegarde absent');
  await upload.send('DOM.setFileInputFiles', {backendNodeId:input.backendNodeId, files:[archive]});
  await upload.detach();
  await frame.getByRole('button',{name:'Vérifier la sauvegarde',exact:true}).click();
  await frame.getByRole('button',{name:'Confirmer la restauration',exact:true}).waitFor({timeout:120000});
  await frame.getByRole('button',{name:'Confirmer la restauration',exact:true}).click();
  await frame.locator('[name="nom_utilisateur"]').waitFor();
  await integrity(550,'École fictive qualification');
  report.afterTransfer = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  pass('ZIP de 550 photos validé par le paquet autonome, réimporté et confirmé dans la PWA');
  await assert.rejects(rpc('ajouter_photos(650)'), /64 Mio/);
  await assert.rejects(rpc('Trace.objects.count()'), /Enregistrement interrompu/);
  killBrowser(); report.restartMs = await boot();
  await integrity(550, 'École fictive qualification');
  pass('Limite réelle de 64 Mio dépassée : runtime bloqué, reprise à 550 photos et intégrité SQLite');
  // Quota imposé par Chromium, sans injection d'une exception dans l'application.
  const cdp = await context.newCDPSession(page);
  const quota = await cdp.send('Storage.getUsageAndQuota', {origin:url.slice(0,-1)});
  await cdp.send('Storage.overrideQuotaForOrigin', {origin:url.slice(0,-1),quotaSize:quota.usage+1024});
  await assert.rejects(rpc("from suivi.models import Ecole; Ecole.objects.update(nom='Quota fictif non confirmé')"), /Quota|quota|espace/i);
  await cdp.send('Storage.overrideQuotaForOrigin', {origin:url.slice(0,-1)});
  killBrowser(); await boot(); await integrity(550,'École fictive qualification');
  pass('Quota Chromium contraint : erreur réelle d’écriture et état précédent retrouvé');
  for (const [phase, expected] of [['before-activate','École fictive qualification'], ['after-activate','École fictive après activation']]) {
    const oldHash = await value("import hashlib; from suivi.models import Trace; hashlib.sha256(Trace.objects.order_by('pk').first().photo.read()).hexdigest()");
    const nextHash = await value("hashlib.sha256(Trace.objects.order_by('pk').first().photo.read()+b'PWA6-interruption').hexdigest()");
    const pending = rpc(`
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from suivi.models import Ecole, Trace
trace=Trace.objects.order_by('pk').first()
old_name=trace.photo.name
payload=trace.photo.read()+b'PWA6-interruption'
trace.photo.save('interruption-fictive.jpg',ContentFile(payload))
default_storage.delete(old_name)
Ecole.objects.update(nom='École fictive après activation')
`, 'pause-'+phase).catch(()=>{});
    await page.waitForFunction(expected => window.pwaCheckpoint === expected, phase, {timeout:120000});
    killBrowser(); await pending; await boot();
    if (phase === 'after-activate') report.photoHashes = report.photoHashes.filter(hash=>hash!==oldHash).concat(nextHash).sort();
    await integrity(550,expected);
    pass(`SIGKILL avant réponse, ${phase} : base et photo remplacée retrouvent ensemble l’état attendu`);
  }
  report.afterRecovery = (await page.evaluate(() => window.pwaTest({kind:'test-metrics'}))).result;
  const files = await page.evaluate(async () => {
    const dir=await (await navigator.storage.getDirectory()).getDirectoryHandle('petits-pas-prototype');
    const names=[]; for await (const [name] of dir.entries()) names.push(name);
    const req=indexedDB.open('petits-pas-pwa-prototype-v1');
    const db=await new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);});
    const get=db.transaction('state').objectStore('state').get('active');
    const active=await new Promise((resolve,reject)=>{get.onsuccess=()=>resolve(get.result); get.onerror=()=>reject(get.error);}); db.close();
    const keep=new Set();
    for (const entry of [active,active.previous,active.recovery].filter(Boolean)) {
      keep.add(entry.file);
      const tree=JSON.parse(await (await (await dir.getFileHandle(entry.file)).getFile()).text());
      for (const file of Object.values(tree.files)) keep.add(file.file);
    }
    return {names:names.sort(), keep:[...keep].sort()};
  });
  assert.deepEqual(files.names, files.keep, 'Fichiers orphelins non nettoyés');
  pass('Manifestes et blobs OPFS orphelins nettoyés après reprise');
  assert(!requests.some(route=>route.startsWith('/app/')));
  pass('Aucune requête métier reçue par le serveur statique');
})().then(()=>{report.status='passed';}).catch(error=>{report.status='failed';report.error=String(error.stack||error);console.error(error);process.exitCode=1;}).finally(async()=>{
  fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  killBrowser(); await browser?.close().catch(()=>{}); server.close();
  fs.rmSync(profile,{recursive:true,force:true});
});
