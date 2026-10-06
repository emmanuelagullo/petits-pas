// Exécuté dans le Worker dédié, avant toute lecture des données de l'école.
export async function checkStorage() {
  if (typeof FileReaderSync !== 'function' || !globalThis.indexedDB || !globalThis.crypto?.subtle)
    throw new Error('Navigateur incompatible : lecture synchrone, IndexedDB et SHA-256 requis.');
  const root = await navigator.storage.getDirectory();
  const name = 'petits-pas-verification-' + crypto.randomUUID();
  let handle, created = false;
  try {
    const file = await root.getFileHandle(name, {create:true});
    created = true;
    if (!file.createSyncAccessHandle) throw new Error('Navigateur incompatible : accès OPFS synchrone requis.');
    handle = await file.createSyncAccessHandle();
    const bytes = new Uint8Array([80, 80, 13]);
    if (handle.write(bytes, {at:0}) !== bytes.length) throw new Error('Écriture OPFS incomplète.');
    handle.flush();
    const read = new Uint8Array(bytes.length);
    if (handle.read(read, {at:0}) !== bytes.length || read.some((value, i) => value !== bytes[i]))
      throw new Error('Lecture OPFS incorrecte.');
    handle.close(); handle = null;
    const readFile = new Uint8Array(new FileReaderSync().readAsArrayBuffer(await file.getFile()));
    if (readFile.length !== bytes.length || readFile.some((value, i) => value !== bytes[i]))
      throw new Error('Lecture des médias OPFS incorrecte.');
  } finally {
    try {handle?.close();} finally {if (created) await root.removeEntry(name);}
  }
}
