// Instantanés immuables OPFS + pointeur transactionnel IndexedDB.
// Aucun accès concurrent : le propriétaire détient un Web Lock dans la coque.
const DB = 'petits-pas-pwa-prototype-v1';
async function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
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
export async function load(version, recovery = false) {
  let current = await state();
  if (recovery) current = current?.recovery || current;
  const root = await navigator.storage.getDirectory();
  const dir = await root.getDirectoryHandle('petits-pas-prototype', {create: true});
  if (!current) return null;
  const file = await (await dir.getFileHandle(current.file)).getFile();
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (await digest(bytes) !== current.hash) throw new Error('Instantané endommagé : ouverture refusée. Aucune école vide ne sera créée.');
  return bytes;
}
export async function save(bytes, version, failpoint = '', preserve = false) {
  if (bytes.byteLength > 16 * 1024 * 1024) throw new Error('Limite expérimentale : instantané supérieur à 16 Mio.');
  const current = await state();
  const root = await navigator.storage.getDirectory();
  const dir = await root.getDirectoryHandle('petits-pas-prototype', {create: true});
  const file = crypto.randomUUID() + '.zip';
  const handle = await (await dir.getFileHandle(file, {create: true})).createSyncAccessHandle();
  try {
    if (failpoint === 'quota') throw new DOMException('Quota simulé', 'QuotaExceededError');
    let written = 0;
    while (written < bytes.length) {
      const count = handle.write(bytes.subarray(written), {at: written});
      if (!count) throw new Error('Écriture OPFS incomplète');
      written += count;
    }
    handle.truncate(bytes.length);
    handle.flush();
  } finally { handle.close(); }
  if (failpoint === 'before-activate') throw new Error('Interruption simulée avant activation');
  const hash = await digest(bytes);
  const recovery = current && (preserve || current.version !== version)
    ? {file: current.file, hash: current.hash, version: current.version}
    : current?.recovery || null;
  await activate({file, hash, version, previous: current?.file || null, recovery});
  // Garder actif + précédent. Les orphelins de panne sont nettoyés après succès.
  for await (const [name] of dir.entries()) {
    if (name !== file && name !== current?.file && name !== recovery?.file) await dir.removeEntry(name).catch(() => {});
  }
  return {bytes: bytes.length, hash};
}
