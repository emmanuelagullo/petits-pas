const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/transport.js'), 'utf8');
const moduleReady = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
test('Une réponse après deux minutes reste acceptée ; le budget reste borné', async () => {
  const {requestWorker, OPERATION_MS} = await moduleReady;
  const original = global.setTimeout, clear = global.clearTimeout;
  let timer, stopped = false, port;
  global.setTimeout = (fn, ms) => {timer = {fn, ms}; return timer;};
  global.clearTimeout = id => {if (id === timer) timer = null;};
  try {
    const result = requestWorker({postMessage(message, ports) {port = ports[0];}}, {}, {onTimeout: () => {stopped = true;}});
    assert.equal(timer.ms, 900000);
    assert(OPERATION_MS > 120000);
    // Horloge virtuelle : après l'ancien délai, aucune expiration.
    let elapsed = 120001;
    if (elapsed >= timer.ms) timer.fn();
    assert.equal(stopped, false);
    elapsed = 130000; assert(elapsed < timer.ms);
    port.postMessage({ok:true, value:'état confirmé'});
    assert.equal(await result, 'état confirmé');
    assert.equal(timer, null); assert.equal(stopped, false); port.close();
  } finally {global.setTimeout = original; global.clearTimeout = clear;}
});
test('Une absence de réponse arrête le moteur et refuse une réponse tardive', async () => {
  const {requestWorker} = await moduleReady;
  let stopped = 0, port;
  const result = requestWorker({postMessage(message, ports) {port = ports[0];}}, {},
    {timeoutMs:10, onTimeout: () => {stopped++;}});
  await assert.rejects(result, /Résultat incertain/);
  assert.equal(stopped, 1);
  port.postMessage({ok:true, value:'trop tard'}); port.close();
});
test('Erreur du Worker et erreur de transport sont transmises sans attendre', async () => {
  const {requestWorker} = await moduleReady;
  await assert.rejects(requestWorker({postMessage(message, ports) {
    ports[0].postMessage({ok:false, error:'Quota dépassé'}); ports[0].close();
  }}, {}), /Quota dépassé/);
  await assert.rejects(requestWorker({postMessage() {throw new Error('Worker fermé');}}, {}), /Worker fermé/);
});

test('Préflight OPFS ferme et supprime sa sonde, y compris après lecture incorrecte', async () => {
  const content = fs.readFileSync(require('node:path').join(__dirname, '../pwa/capabilities.js'), 'utf8');
  const {checkStorage} = await import('data:text/javascript;base64,' + Buffer.from(content).toString('base64'));
  const names = ['navigator', 'FileReaderSync', 'indexedDB', 'crypto'];
  const descriptors = names.map(name => Object.getOwnPropertyDescriptor(global, name));
  let created, closed = 0, removed = [], wrong = false;
  const handle = {write:bytes => bytes.length, flush() {},
    read(bytes) {bytes.set(wrong ? [0,0,0] : [80,80,13]); return bytes.length;},
    close() {closed++;}};
  const root = {async getFileHandle(name) {created = name; return {
    async createSyncAccessHandle() {return handle;}, async getFile() {return {};},
  };}, async removeEntry(name) {removed.push(name);}};
  try {
    for (const [name, value] of Object.entries({navigator:{storage:{getDirectory:async()=>root}},
      indexedDB:{}, crypto:{subtle:{},randomUUID:()=> 'uuid-fictif'},
      FileReaderSync:class {readAsArrayBuffer() {return new Uint8Array([80,80,13]).buffer;}}}))
      Object.defineProperty(global, name, {value, configurable:true, writable:true});
    await checkStorage();
    assert.equal(closed, 1); assert.deepEqual(removed, [created]);
    assert.equal(created, 'petits-pas-verification-uuid-fictif');
    wrong = true;
    await assert.rejects(checkStorage(), /Lecture OPFS incorrecte/);
    assert.equal(closed, 2); assert.equal(removed.length, 2);
    global.FileReaderSync = undefined;
    await assert.rejects(checkStorage(), /Navigateur incompatible/);
    assert.equal(removed.length, 2);
  } finally {
    names.forEach((name,i) => {if (descriptors[i]) Object.defineProperty(global,name,descriptors[i]); else delete global[name];});
  }
});
