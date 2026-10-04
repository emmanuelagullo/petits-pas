import {load, save, configurerEspace} from './storage.js';
let ESSAI = false;
let APERCU = false;
const BASE = new URL('./', import.meta.url).pathname;
let python, bridge, config, fatal = false, initialized = false;
let queue = Promise.resolve();
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
  }, config.version, failpoint, preserve, force);
  // Le secours durable reste dans OPFS ; libérer la copie MEMFS remplacée.
  call('release_previous_package');
  return {...result, snapshotMs, persistMs: performance.now() - started};
}
async function process(message) {
  if (fatal) throw new Error('Enregistrement interrompu. Fermez puis rouvrez le prototype pour retrouver le dernier état confirmé.');
  if (['init', 'recovery'].includes(message.kind)) {
    if (initialized) throw new Error('Runtime déjà initialisé');
    ESSAI = message.essai === true;
    APERCU = message.apercu === true;
    if (APERCU) ESSAI = false;
    configurerEspace(ESSAI, APERCU);
    config = await (await fetch('./config.json')).json();
    const started = performance.now();
    progress("Lecture des données conservées sur cet appareil…");
    const restored = await load(config.version, message.kind === 'recovery');
    if (message.kind === 'recovery' && !restored) throw new Error("Aucune donnée locale à exporter.");
    progress('Chargement du moteur Python…');
    const {loadPyodide} = await import('./runtime/pyodide.mjs');
    python = await loadPyodide({indexURL: new URL('./runtime/', location.href).href});
    progress("Préparation des bibliothèques…");
    await python.loadPackage(['sqlite3', 'pillow', 'pyyaml', 'micropip', 'hashlib']);
    // hashlib a pu être importé par Pyodide avant le chargement de _hashlib.
    python.runPython('import hashlib, importlib; importlib.reload(hashlib)');
    const micropip = python.pyimport('micropip');
    try { await micropip.install(config.wheels.map(name => new URL('./wheels/' + name, location.href).href)); }
    finally { micropip.destroy(); }
    const app = new Uint8Array(await (await fetch('./application.zip')).arrayBuffer());
    python.unpackArchive(app, 'zip', {extractDir: '/application'});
    python.runPython("import sys; sys.path.insert(0, '/application')");
    bridge = python.pyimport('pwa.bridge');
    if (restored?.files) {
      for (const [name, entry] of Object.entries(restored.files)) call('restore_file', name, await restored.read(entry));
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
      const proxy = call('snapshot');
      try { return {bytes: proxy.toJs()}; } finally { proxy.destroy(); }
    }
    progress('Ouverture de l’école et vérification de la base…');
    call('initialize', location.origin, config.version, BASE, ESSAI, APERCU);
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
  if (message.kind === 'test-metrics' && config.testMode) {
    return {result: {...JSON.parse(call('metrics')), wasmHeapBytes: python._module?.HEAP8?.byteLength || null}};
  }
  let result;
  if (message.kind === 'checkpoint') {
    try { return {durability: await persist('', false, true)}; }
    catch (error) { fatal = true; throw error; }
  }
  if (message.kind === 'http') {
    const url = new URL(message.request.url);
    if (url.origin !== location.origin || !url.pathname.startsWith(BASE + 'app/')) throw new Error('Origine ou route refusée');
    try {
      const {body, ...metadata} = message.request;
      const bytes = typeof body === 'string' ? Uint8Array.from(atob(body), c => c.charCodeAt(0)) : body;
      result = JSON.parse(call('handle', JSON.stringify(metadata), bytes));
      const proxy = call('response_bytes');
      try {result.body = proxy.toJs();} finally {proxy.destroy();}
    }
    catch (error) { fatal = true; throw error; }
  } else if (message.kind === 'test-python' && config.testMode) {
    result = python.runPython(message.code);
    if (result?.destroy) { result.destroy(); result = null; }
  } else { throw new Error('Commande refusée'); }
  try {
    const durability = await persist(config.testMode ? (message.failpoint || '') : '', !!result?.restored,
      false, message.kind === 'test-python');
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
    return {result, durability};
  } catch (error) { fatal = true; throw error; }
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
