// Fichiers et manifestes immuables OPFS + pointeur transactionnel IndexedDB.
// Aucun accès concurrent : le propriétaire détient un Web Lock dans la coque.
const BASE = new URL('./', import.meta.url).pathname;
const PREFIXE = BASE === '/' ? '' : '-' + encodeURIComponent(BASE);
let SUFFIX = PREFIXE;
export function configurerEspace(essai, apercu = false) { SUFFIX = PREFIXE + (apercu ? '-apercu' : (essai ? '-essai' : '')); }
async function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('petits-pas-pwa-prototype-v1' + SUFFIX, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('state');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function state() {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction('state').objectStore('state').get('active');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally { db.close(); }
}
async function activate(value) {
  const db = await database();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction('state', 'readwrite', {durability: 'strict'});
      tx.objectStore('state').put(value, 'active');
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error('Activation annulée'));
    });
  } finally { db.close(); }
}
async function digest(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    b => b.toString(16).padStart(2, '0')).join('');
}
// Le format 1 (ZIP) reste lisible pour la mise à jour et le secours.
const LIMIT = 64 * 1024**2;
async function directory() {
  return (await navigator.storage.getDirectory()).getDirectoryHandle('petits-pas-prototype' + SUFFIX, {create: true});
}
function descriptor(value) {
  if (!value) return null;
  const {format, file, hash, version, bytes} = value;
  return {format, file, hash, version, bytes};
}
async function checked(dir, entry) {
  if (!/^[a-zA-Z0-9-]+\.(zip|json|blob)$/.test(entry.file)) throw new Error('Nom OPFS invalide');
  const bytes = new Uint8Array(await (await (await dir.getFileHandle(entry.file)).getFile()).arrayBuffer());
  if ((entry.size !== undefined && bytes.length !== entry.size) || await digest(bytes) !== entry.hash)
    throw new Error('État local endommagé : ouverture refusée. Aucune école vide ne sera créée.');
  return bytes;
}
function validName(name) {
  return (['carnet.sqlite3', 'secret-key', 'suivi-sauvegarde.json'].includes(name) || name.startsWith('media/'))
    && !name.includes('\\') && name.split('/').every(part => part && !['.', '..'].includes(part));
}
async function manifest(dir, entry) {
  if (entry?.format !== 2) return null;
  const value = JSON.parse(new TextDecoder().decode(await checked(dir, entry)));
  if (value.format !== 2 || !value.files || Array.isArray(value.files)
      || !value.files['carnet.sqlite3'] || !value.files['secret-key']) throw new Error('Manifeste local invalide');
  let size = 0;
  for (const [name, file] of Object.entries(value.files)) {
    if (!validName(name) || !/^[a-f0-9]{64}$/.test(file.hash) || !Number.isSafeInteger(file.size) || file.size < 0)
      throw new Error('Fichier local invalide');
    size += file.size;
  }
  if (size > LIMIT || Object.keys(value.files).length + 1 > 5000) throw new Error('État local trop volumineux');
  return value;
}
export async function load(version, recovery = false) {
  let current = await state();
  if (recovery) current = current?.recovery || current;
  if (!current) return null;
  const dir = await directory();
  const tree = await manifest(dir, current);
  // Le Worker lit une photo à la fois : aucun ZIP intermédiaire à l'ouverture.
  if (tree) return {files: tree.files, read: entry => checked(dir, entry),
    file: async entry => (await dir.getFileHandle(entry.file)).getFile()};
  return checked(dir, current);
}
async function write(dir, bytes, suffix, failpoint) {
  const file = crypto.randomUUID() + suffix;
  const handle = await (await dir.getFileHandle(file, {create: true})).createSyncAccessHandle();
  try {
    if (failpoint === 'quota') throw new DOMException('Quota simulé', 'QuotaExceededError');
    let written = 0;
    while (written < bytes.length) {
      const count = handle.write(bytes.subarray(written), {at: written});
      if (!count) throw new Error('Écriture OPFS incomplète');
      written += count;
    }
    handle.truncate(bytes.length); handle.flush();
  } finally {handle.close();}
  return {file, hash: await digest(bytes), size: bytes.length};
}
async function pause(failpoint, phase) {
  if (failpoint === 'pause-' + phase) {
    self.postMessage({kind: 'test-checkpoint', phase});
    await new Promise(() => {});
  }
  if (failpoint === phase) throw new Error('Interruption simulée ' + phase);
}
async function clean(dir, references) {
  const keep = new Set();
  for (const entry of references.filter(Boolean)) {
    keep.add(entry.file);
    const tree = await manifest(dir, entry);
    for (const file of Object.values(tree?.files || {})) keep.add(file.file);
  }
  for await (const [name] of dir.entries()) {
    if (!keep.has(name)) await dir.removeEntry(name).catch(() => {});
  }
}
export async function save(inventory, read, version, failpoint = '', preserve = false, force = false) {
  // L'inventaire compte aussi le manifeste ZIP public pour sa réimportation.
  const {files, bytes} = inventory;
  if (bytes > LIMIT || Object.keys(files).length + 1 > 5000) throw new Error('Limite expérimentale : état supérieur à 64 Mio ou 5 000 fichiers.');
  const current = await state();
  const dir = await directory();
  const tree = await manifest(dir, current);
  const unchanged = tree && Object.keys(tree.files).length === Object.keys(files).length
    && Object.entries(files).every(([name, file]) => tree.files[name]?.hash === file.hash && tree.files[name]?.size === file.size);
  if (unchanged && current.version === version && !preserve && !force && !failpoint)
    return {bytes, hash: current.hash, changed: false, writtenBytes: 0, writtenFiles: 0};
  // Réutiliser les blobs de l'état actif ; aucun fichier référencé n'est écrasé.
  const pool = new Map(Object.values(tree?.files || {}).map(file => [file.hash, file]));
  const next = {}; let writtenBytes = 0, writtenFiles = 0;
  for (const [name, file] of Object.entries(files)) {
    let entry = pool.get(file.hash);
    if (!entry) {
      const content = read(name);
      if (content.length !== file.size || await digest(content) !== file.hash) throw new Error('Fichier modifié pendant la sauvegarde');
      entry = await write(dir, content, '.blob', failpoint);
      pool.set(file.hash, entry); writtenBytes += content.length; writtenFiles++;
    }
    next[name] = entry;
  }
  const content = new TextEncoder().encode(JSON.stringify({format: 2, files: next}));
  const saved = await write(dir, content, '.json', failpoint);
  writtenBytes += content.length;
  await pause(failpoint, 'before-activate');
  const recovery = current && (preserve || current.version !== version)
    ? descriptor(current) : current?.recovery || null;
  const active = {format: 2, file: saved.file, hash: saved.hash, version, bytes,
    previous: descriptor(current), recovery};
  await activate(active);
  await pause(failpoint, 'after-activate');
  // Une erreur de nettoyage après commit ne doit pas annoncer une saisie perdue.
  await clean(dir, [active, active.previous, recovery]).catch(() => {});
  return {bytes, hash: saved.hash, changed: true, writtenBytes, writtenFiles};
}

// Après confirmation seulement : les File désignent des blobs qui ne seront
// jamais modifiés. Le manifeste actif/précédent/secours gouverne leur nettoyage.
export async function confirmedMedia() {
  const dir = await directory();
  const tree = await manifest(dir, await state());
  return {files: tree?.files || {}, file: async entry => (await dir.getFileHandle(entry.file)).getFile()};
}
