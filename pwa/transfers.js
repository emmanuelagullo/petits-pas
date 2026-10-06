// Un seul Worker exclusif ; au plus requête, upload, export et média en écriture.
const BASE = new URL('./', import.meta.url).pathname;
const PREFIX = 'petits-pas-transferts-' + encodeURIComponent(BASE);
const handles = new Map();
const counters = {maxIoBlockBytes:0, maxRequestBlockBytes:0};
export function transferMetrics() {return {...counters, openTransferHandles:handles.size};}
export function installIO() {
  function bufferCall(key, buffer, at, method) {
    const view = buffer.getBuffer('u8');
    counters.maxIoBlockBytes = Math.max(counters.maxIoBlockBytes, view.data.length);
    try {return handles.get(key)[method](view.data, {at});}
    finally {view.release();}
  }
  self.pwaIO = {
    size: key => handles.get(key).getSize(),
    flush: key => handles.get(key).flush(),
    read: (key, buffer, at) => bufferCall(key, buffer, at, 'read'),
    write: (key, buffer, at) => {
      let position = 0;
      const view = buffer.getBuffer('u8');
      counters.maxIoBlockBytes = Math.max(counters.maxIoBlockBytes, view.data.length);
      try {
        while (position < view.data.length) {
          const count = handles.get(key).write(view.data.subarray(position), {at:at + position});
          if (!count) throw new Error('Écriture OPFS interrompue');
          position += count;
        }
        return position;
      } finally {view.release();}
    },
  };
}
export function setHandle(key, handle) {handles.set(key, handle);}
export function closeHandle(key) {
  const handle = handles.get(key);
  if (handle) {handle.flush(); handle.close(); handles.delete(key);}
}
export async function beginTransfers() {
  const root = await (await navigator.storage.getDirectory()).getDirectoryHandle(PREFIX, {create:true});
  // Export interrompu : conserver les téléchargements récents ; ménage borné à
  // plus d'un jour, sans confondre ces temporaires avec les données de l'école.
  for await (const [name] of root.entries()) {
    if (/^\d+-/.test(name) && Number(name.split('-')[0]) < Date.now() - 86400000)
      await root.removeEntry(name, {recursive:true});
  }
  const token = Date.now() + '-' + crypto.randomUUID();
  const dir = await root.getDirectoryHandle(token, {create:true});
  const opened = [];
  try {
    for (const key of ['request', 'upload', 'export']) {
      const handle = await (await dir.getFileHandle(key, {create:true})).createSyncAccessHandle();
      setHandle(key, handle); opened.push(key);
    }
  } catch (error) {
    for (const key of opened) closeHandle(key);
    await root.removeEntry(token, {recursive:true}).catch(()=>{});
    throw error;
  }
  return {root, dir, token};
}
export async function endTransfers(context, keepExport = false) {
  for (const key of ['request', 'upload', 'export', 'media']) closeHandle(key);
  if (keepExport) {
    await context.dir.removeEntry('request'); await context.dir.removeEntry('upload');
    return {file:await (await context.dir.getFileHandle('export')).getFile(), token:context.token};
  }
  await context.root.removeEntry(context.token, {recursive:true});
  return null;
}
export async function releaseExport(token) {
  if (!/^\d+-[a-f0-9-]+$/.test(token)) throw new Error('Référence de téléchargement invalide');
  const root = await (await navigator.storage.getDirectory()).getDirectoryHandle(PREFIX, {create:true});
  await root.removeEntry(token, {recursive:true});
}
export async function receiveBody(port) {
  let bytes = 0;
  try {
    await new Promise((resolve, reject) => {
      port.onmessage = event => {
        try {
          if (event.data.done) {handles.get('request').flush(); resolve(); return;}
          const block = event.data.bytes;
          if (!(block instanceof Uint8Array) || block.length > 1024**2 || bytes + block.length > 270 * 1024**2)
            throw new Error('Envoi supérieur à 270 Mio ou bloc invalide');
          counters.maxRequestBlockBytes = Math.max(counters.maxRequestBlockBytes, block.length);
          let written = 0;
          while (written < block.length) {
            const count = handles.get('request').write(block.subarray(written), {at:bytes + written});
            if (!count) throw new Error('Écriture du transfert interrompue');
            written += count;
          }
          bytes += block.length; port.postMessage({next:true});
        } catch (error) {port.postMessage({error:String(error)}); reject(error);}
      };
      port.start(); port.postMessage({next:true});
    });
  } finally {port.close();}
  return bytes;
}
