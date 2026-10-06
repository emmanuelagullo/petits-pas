import {checkStorage} from './capabilities.js';
import {load, save, configurerEspace, confirmedMedia, openStagedMedia, clearStagedMedia} from './storage.js';
import {mediaFiles} from './lazy_media.js';
import {installIO, beginTransfers, endTransfers, receiveBody, setHandle, closeHandle, releaseExport, transferMetrics} from './transfers.js';
installIO();
let ESSAI = false;
let APERCU = false;
const BASE = new URL('./', import.meta.url).pathname;
let python, bridge, config, media, fatal = false, initialized = false;
let queue = Promise.resolve();
let pauseTransfer = false;
function progress(text) { self.postMessage({kind: 'progress', text}); }
function call(name, ...args) {
  const method = bridge[name];
  try { return method(...args); } finally { method.destroy(); }
}
async function persist(failpoint = '', preserve = false, force = false, scan = false) {
  const started = performance.now();
  const files = JSON.parse(call('inventory', scan));
  const snapshotMs = performance.now() - started;
  const result = await save(files, name => {
    const proxy = call('file_bytes', name);
    try {return proxy.toJs();} finally {proxy.destroy();}
  }, config.version, failpoint, preserve, force, (name, hash) => media.entry('/data/' + name, hash));
  // Retirer les buffers des seuls médias nouveaux/modifiés après activation.
  const confirmed = await confirmedMedia();
  for (const [name, entry] of Object.entries(confirmed.files)) {
    if (name.startsWith('media/') && !media.isBound('/data/' + name, entry.hash))
      media.bind('/data/' + name, await confirmed.file(entry), entry.hash);
  }
  // Le secours durable reste dans OPFS ; libérer la copie MEMFS remplacée.
  call('release_previous_package');
  return {...result, snapshotMs, persistMs: performance.now() - started};
}
async function process(message) {
  if (fatal) throw new Error('Enregistrement interrompu. Fermez puis rouvrez Petits Pas pour retrouver le dernier état confirmé.');
  if (['init', 'recovery'].includes(message.kind)) {
    if (initialized) throw new Error('Runtime déjà initialisé');
    ESSAI = message.essai === true;
    APERCU = message.apercu === true;
    if (APERCU) ESSAI = false;
    await checkStorage();
    configurerEspace(ESSAI, APERCU);
    config = await (await fetch('./config.json')).json();
    const started = performance.now();
    progress("Lecture des données conservées sur cet appareil…");
    const restored = await load(config.version, message.kind === 'recovery');
    if (message.kind === 'recovery' && !restored) throw new Error("Aucune donnée locale à exporter.");
    progress('Chargement du moteur Python…');
    const {loadPyodide, version: runtimeVersion} = await import('./runtime/pyodide.mjs');
    if (runtimeVersion !== config.pyodide) throw new Error('Runtime local incohérent. Republiez le bundle complet ; ne supprimez pas les données du navigateur.');
    python = await loadPyodide({indexURL: new URL('./runtime/', location.href).href});
    progress("Préparation des bibliothèques…");
    await python.loadPackage(['pillow', 'pyyaml', 'micropip', 'pycryptodome']);

    const micropip = python.pyimport('micropip');
    try { await micropip.install(config.wheels.map(name => new URL('./wheels/' + name, location.href).href)); }
    finally { micropip.destroy(); }
    const app = new Uint8Array(await (await fetch('./application.zip')).arrayBuffer());
    python.unpackArchive(app, 'zip', {extractDir: '/application'});
    python.runPython("import sys; sys.path.insert(0, '/application')");
    // Limiter aussi ImageField Django aux formats proposés par Petits Pas.
    python.runPython("from PIL import Image; Image.init(); Image.ID[:] = [name for name in Image.ID if name in ('JPEG', 'PNG', 'WEBP')]");
    python.runPython('from pwa.crypto import configure; configure()');
    bridge = python.pyimport('pwa.bridge');
    media = mediaFiles(python.FS);
    if (restored?.files) {
      for (const [name, entry] of Object.entries(restored.files)) {
        if (name.startsWith('media/')) {
          // Vérification transitoire, une photo à la fois ; aucune copie MEMFS.
          await restored.read(entry);
          media.bind('/data/' + name, await restored.file(entry), entry.hash);
        } else call('restore_file', name, await restored.read(entry));
      }
      call('restore_media_index', JSON.stringify(restored.files));
    } else if (restored) call('restore', restored);
    else if (APERCU) throw new Error("Aucun ZIP à vérifier dans cet espace. Revenez à l’école habituelle pour ouvrir une copie.");
    else if (ESSAI && message.kind === 'init') {
      const reponse = await fetch('./ecole-fictive.zip');
      if (!reponse.ok) throw new Error("École fictive indisponible dans cette version.");
      const archive = new Uint8Array(await reponse.arrayBuffer());
      const attendu = config.assets.find(asset => asset.url === '/ecole-fictive.zip')?.sha256;
      const somme = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', archive)), b => b.toString(16).padStart(2, '0')).join('');
      if (!attendu || somme !== attendu) throw new Error("ZIP fictif altéré : ouverture refusée.");
      call('restore_demo', archive);
    }
    if (message.kind === 'recovery') {
      const context = await beginTransfers();
      try {call('snapshot'); return await endTransfers(context, true);}
      catch (error) {await endTransfers(context); throw error;}
    }
    progress('Ouverture de l’école et vérification de la base…');
    call('initialize', location.origin, config.application_version || config.version, BASE, ESSAI, APERCU);
    progress('Enregistrement de l’état initial…');
    const durability = await persist('', false, true);
    initialized = true;
    let apercuDisponible = false;
    configurerEspace(false, true);
    try {apercuDisponible = !!(await load());}
    catch { /* Une copie endommagée ne bloque pas l'école habituelle. */ }
    finally {configurerEspace(ESSAI, APERCU);}
    return {durationMs: performance.now() - started, restored: !!restored, durability, apercuDisponible};
  }
  if (!initialized) throw new Error('Runtime indisponible');
  if (message.kind === 'release-export') {
    await releaseExport(message.token); return {};
  }
  if (message.kind === 'test-pause-transfer' && config.testMode) {pauseTransfer = true; return {};}
  if (message.kind === 'test-metrics' && config.testMode) {
    return {result: {...JSON.parse(call('metrics')), ...media.metrics(), ...transferMetrics(), wasmHeapBytes: python._module?.HEAP8?.byteLength || null}};
  }
  let result, transferContext;
  if (message.kind === 'checkpoint') {
    try { return {durability: await persist('', false, true)}; }
    catch (error) { fatal = true; throw error; }
  }
  if (message.kind === 'http') {
    const url = new URL(message.request.url);
    if (url.origin !== location.origin || !url.pathname.startsWith(BASE + 'app/')) throw new Error('Origine ou route refusée');
    try {
      const {body, inputPort, ...metadata} = message.request;
      const multipart = metadata.headers.some(([key, value]) => key.toLowerCase() === 'content-type' && value.startsWith('multipart/form-data'));
      if (inputPort || multipart || (metadata.method === 'POST' && url.pathname.endsWith('/gestion/sauvegardes-locales/')))
        transferContext = await beginTransfers();
      if (inputPort) {await receiveBody(inputPort); metadata.opfs_input = true;}
      const bytes = typeof body === 'string' ? Uint8Array.from(atob(body), c => c.charCodeAt(0)) : body;
      result = JSON.parse(call('handle', JSON.stringify(metadata), bytes));
      if (result.job) {
        progress('Vérification et préparation du ZIP, fichier par fichier…');
        let staged;
        for (;;) {
          const step = JSON.parse(call('transfer_step'));
          if (step.phase === 'termine') break;
          if (step.phase === 'ouvrir') {
            if (step.media) {staged = await openStagedMedia(); setHandle('media', staged.handle);}
          } else if (step.media) {
            closeHandle('media');
            const file = await (await staged.dir.getFileHandle(staged.file)).getFile();
            media.bind(step.chemin, file, step.hash, {file:staged.file, hash:step.hash, size:file.size});
            staged = null;
            if (pauseTransfer && config.testMode) {
              pauseTransfer = false;
              self.postMessage({kind:'test-checkpoint', phase:'transfer-media'});
              await new Promise(() => {});
            }
          }
        }
        closeHandle('media');
        result = JSON.parse(call('finish_transfer', JSON.stringify(result)));
      }
      const proxy = call('response_bytes');
      try {result.body = proxy.toJs();} finally {proxy.destroy();}
    }
    catch (error) {
      if (transferContext) await endTransfers(transferContext).catch(()=>{});
      fatal = true; throw error;
    }
  } else if (message.kind === 'test-python' && config.testMode) {
    result = python.runPython(message.code);
    if (result?.destroy) { result.destroy(); result = null; }
  } else { throw new Error('Commande refusée'); }
  try {
    const durability = await persist(config.testMode ? (message.failpoint || '') : '', !!result?.restored,
      false, message.kind === 'test-python' && message.scan !== false);
    if (result?.ouvrir_apercu) {
      configurerEspace(false, true);
      try {
        const files = JSON.parse(call('inventory_apercu'));
        await save(files, name => {
          const proxy = call('file_bytes_apercu', name);
          try {return proxy.toJs();} finally {proxy.destroy();}
        }, config.version, '', false, true);
        call('nettoyer_apercu');
      } finally {configurerEspace(ESSAI, APERCU);}
    }
    if (!call('has_preparation')) await clearStagedMedia();
    if (transferContext) {
      const exported = await endTransfers(transferContext, result.export);
      if (exported) {
        Object.assign(result, exported);
        result.headers = result.headers.filter(([key]) => key.toLowerCase() !== 'content-length');
        result.headers.push(['Content-Length', String(exported.file.size)]);
      }
    }
    return {result, durability};
  } catch (error) {
    if (transferContext) await endTransfers(transferContext).catch(()=>{});
    fatal = true; throw error;
  }
}
self.onmessage = event => {
  const port = event.ports[0];
  if (!port) return;
  queue = queue.then(async () => {
    try {
      const value = await process(event.data);
      const bytes = value.result?.body || value.bytes;
      port.postMessage({ok: true, value}, bytes?.buffer ? [bytes.buffer] : []);
    }
    catch (error) { port.postMessage({ok: false, error: String(error.stack || error)}); }
    finally { port.close(); }
  });
};
