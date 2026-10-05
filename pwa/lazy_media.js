// Métadonnées MEMFS, contenu File OPFS immuable. Pas de cache de lecture.
// WORKERFS fournit les lectures synchrones par tranches dans ce seul Worker.
export function mediaFiles(FS) {
  const worker = FS.filesystems.WORKERFS;
  if (!worker || typeof FileReaderSync === 'undefined')
    throw new Error('Lecture locale des médias indisponible dans ce navigateur.');
  FS.mkdirTree('/.pwa-workerfs');
  FS.mount(worker, {blobs: []}, '/.pwa-workerfs'); // initialise son FileReaderSync
  let readBytes = 0, materializedBytes = 0;
  function materialize(node, empty = false) {
    if (!node.pwaBlob) return;
    const blob = node.pwaBlob;
    node.contents = empty ? new Uint8Array(0)
      : new Uint8Array(worker.reader.readAsArrayBuffer(blob));
    materializedBytes += node.contents.length;
    node.usedBytes = node.contents.length;
    delete node.pwaBlob;
    delete node.pwaHash;
  }
  function bind(path, blob, hash) {
    FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
    let node;
    try {node = FS.lookupPath(path).node;}
    catch (error) {
      if (error.errno !== 44) throw error; // ENOENT, version Emscripten épinglée
      FS.writeFile(path, new Uint8Array(0));
      node = FS.lookupPath(path).node;
    }
    if (!FS.isFile(node.mode)) throw new Error('Média local non régulier');
    if (node.pwaHash === hash) return;
    // Aucun descripteur Python ne doit survivre au point de confirmation.
    if (FS.streams.some(stream => stream?.node === node))
      throw new Error('Média encore ouvert à la confirmation');
    if (!node.pwaOperations) {
      const streams = node.stream_ops, operations = node.node_ops;
      node.pwaOperations = true;
      node.stream_ops = {...streams,
        read(stream, buffer, offset, length, position) {
          if (!stream.node.pwaBlob) return streams.read(stream, buffer, offset, length, position);
          // Déléguer à WORKERFS sans remplacer les opérations de répertoire MEMFS.
          const count = worker.stream_ops.read({node: {
            contents: stream.node.pwaBlob, size: stream.node.usedBytes,
          }}, buffer, offset, length, position);
          readBytes += count;
          return count;
        },
        write(stream, ...args) {materialize(stream.node); return streams.write(stream, ...args);},
        allocate(stream, ...args) {materialize(stream.node); return streams.allocate(stream, ...args);},
        mmap(stream, ...args) {materialize(stream.node); return streams.mmap(stream, ...args);},
      };
      node.node_ops = {...operations, setattr(node, attributes) {
        if (attributes.size !== undefined) materialize(node, attributes.size === 0);
        return operations.setattr(node, attributes);
      }};
    }
    node.contents = null;
    node.usedBytes = blob.size;
    node.pwaBlob = blob;
    node.pwaHash = hash;
  }
  function isBound(path, hash) {
    try {return FS.lookupPath(path).node.pwaHash === hash;}
    catch {return false;}
  }
  function metrics() {
    let lazyMediaBytes = 0, lazyMediaFiles = 0, residentMediaBytes = 0;
    function walk(node) {
      if (FS.isDir(node.mode)) {
        for (const child of Object.values(node.contents)) walk(child);
      } else if (node.pwaBlob) {
        lazyMediaBytes += node.pwaBlob.size; lazyMediaFiles++;
      } else if (FS.isFile(node.mode)) residentMediaBytes += node.usedBytes;
    }
    try {walk(FS.lookupPath('/data/media').node);} catch { /* paquet neuf */ }
    return {lazyMediaBytes, lazyMediaFiles, residentMediaBytes,
      mediaReadBytes: readBytes, mediaMaterializedBytes: materializedBytes};
  }
  return {bind, isBound, metrics};
}
