const BASE = new URL('./', self.location.href).pathname;
const assetURL = path => BASE + path.replace(/^\//, '');
const CACHE = 'petits-pas-pwa-' + BASE + '__BUILD__';
self.addEventListener('install', event => event.waitUntil((async () => {
  const config = await (await fetch(assetURL('/config.json'), {cache: 'no-store'})).json();
  const cache = await caches.open(CACHE);
  await cache.put(assetURL('/config.json'), new Response(JSON.stringify(config), {headers: {'Content-Type': 'application/json'}}));
  for (const asset of config.assets) {
    const response = await fetch(assetURL(asset.url), {cache: 'no-store'});
    if (!response.ok) throw new Error('Fichier absent : ' + asset.url);
    const bytes = await response.clone().arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== asset.sha256) throw new Error('Empreinte incorrecte : ' + asset.url);
    await cache.put(assetURL(asset.url), response);
  }
})()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
async function local(request) {
  const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: false});
  const owners = clients.filter(client => {
    const url = new URL(client.url);
    return url.origin === self.location.origin && [BASE, BASE + 'index.html'].includes(url.pathname);
  });
  // Le shell possédant le verrou est le seul autorisé ; les onglets bloqués ne
  // démarrent pas d'iframe. Demander à tous les shells n'est jamais acceptable.
  let owner = null;
  for (const client of owners) {
    if (await hasRuntime(client)) { if (owner) throw new Error('Plusieurs propriétaires'); owner = client; }
  }
  if (!owner) return new Response('Ouvrez Petits Pas depuis sa page d’accueil.', {status: 503});
  const channel = new MessageChannel();
  const progressive = request.method === 'POST' && request.headers.get('content-type')?.startsWith('multipart/form-data');
  const upload = progressive ? new MessageChannel() : null;
  const raw = progressive || request.method === 'GET' || request.method === 'HEAD' ? new ArrayBuffer(0) : await request.arrayBuffer();
  if (raw.byteLength > 70 * 1024**2) return new Response('Envoi trop volumineux (70 Mio).', {status: 413});
  const body = new Uint8Array(raw);
  let uploadReader;
  const stopUpload = () => {
    uploadReader?.cancel().catch(() => {});
    upload.port1.close();
  };
  if (upload) {
    // Une tranche est envoyée seulement après consommation de la précédente.
    const reader = uploadReader = request.body.getReader();
    let pending = null, offset = 0;
    upload.port1.onmessage = async event => {
      try {
        if (event.data.error) throw new Error(event.data.error);
        if (!pending || offset === pending.length) {
          const item = await reader.read();
          if (item.done) {upload.port1.postMessage({done:true}); reader.releaseLock(); uploadReader = null; upload.port1.close(); return;}
          pending = item.value; offset = 0;
        }
        const bytes = pending.slice(offset, offset + 1024**2); offset += bytes.length;
        upload.port1.postMessage({bytes}, [bytes.buffer]);
      } catch (error) {await reader.cancel().catch(()=>{}); upload.port1.postMessage({error:String(error)}); upload.port1.close();}
    };
    upload.port1.start();
  }
  const headers = [...request.headers];
  // Le référent géré par le navigateur peut être absent de Request.headers.
  // Transmettre sa valeur réelle, sans inventer un référent si la politique
  // du navigateur l'a supprimé ; Django conserve tous ses contrôles CSRF.
  if (!request.headers.has('referer') && /^https?:\/\//i.test(request.referrer)) {
    headers.push(['Referer', request.referrer]);
  }
  return new Promise(resolve => {
    const timeout = setTimeout(() => { if (upload) stopUpload(); channel.port1.close(); resolve(new Response('Transport interrompu ; résultat incertain. Fermez puis rouvrez Petits Pas.', {status: 503})); }, 16 * 60 * 1000);
    channel.port1.onmessage = event => {
      clearTimeout(timeout); if (upload) stopUpload(); channel.port1.close();
      const r = event.data;
      if (!r.ok) { resolve(new Response(r.error, {status: 507})); return; }
      let content = r.body;
      if (r.file) {
        const reader = r.file.stream().getReader();
        const release = () => owner.postMessage({kind:'release-export', token:r.token});
        content = new ReadableStream({
          async pull(controller) {
            try {const item = await reader.read(); if (item.done) {controller.close(); release();} else controller.enqueue(item.value);}
            catch (error) {controller.error(error); release();}
          },
          async cancel() {await reader.cancel(); release();},
        });
      }
      resolve(new Response(request.method === 'HEAD' || [204, 304].includes(r.status) ? null : content, {status: r.status, headers: r.headers}));
    };
    owner.postMessage({kind: 'http', request: {url: request.url, method: request.method, headers, body,
      ...(upload ? {inputPort:upload.port2} : {})}}, [channel.port2, raw, ...(upload ? [upload.port2] : [])]);
  });
}
async function hasRuntime(client) {
  return new Promise(resolve => {
    const channel = new MessageChannel();
    const timeout = setTimeout(() => {channel.port1.close(); resolve(false);}, 1000);
    channel.port1.onmessage = event => {clearTimeout(timeout); channel.port1.close(); resolve(event.data === true);};
    client.postMessage({kind: 'owner'}, [channel.port2]);
  });
}
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(BASE)) return;
  if (url.pathname.startsWith(BASE + 'app/')) {
    event.respondWith(local(event.request).catch(() => new Response('Transport local interrompu.', {status: 503})));
  } else {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const response = await cache.match(url.pathname === BASE ? BASE + 'index.html' : url.pathname);
      return response || new Response('Ressource absente de Petits Pas hors ligne.', {status: 404});
    })());
  }
});

// Activation explicite après arrêt du runtime par la coque propriétaire.
self.addEventListener('message', event => {
  if (event.data?.kind === 'activate-update') event.waitUntil(self.skipWaiting());
});
