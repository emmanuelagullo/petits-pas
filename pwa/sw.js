const CACHE = 'petits-pas-pwa-' + '__BUILD__';
self.addEventListener('install', event => event.waitUntil((async () => {
  const config = await (await fetch('/config.json', {cache: 'no-store'})).json();
  const cache = await caches.open(CACHE);
  await cache.put('/config.json', new Response(JSON.stringify(config), {headers: {'Content-Type': 'application/json'}}));
  for (const asset of config.assets) {
    const response = await fetch(asset.url, {cache: 'no-store'});
    if (!response.ok) throw new Error('Fichier absent : ' + asset.url);
    const bytes = await response.clone().arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== asset.sha256) throw new Error('Empreinte incorrecte : ' + asset.url);
    await cache.put(asset.url, response);
  }
})()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
async function local(request) {
  const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: false});
  const owners = clients.filter(client => {
    const url = new URL(client.url);
    return url.origin === self.location.origin && ['/', '/index.html'].includes(url.pathname);
  });
  // Le shell possédant le verrou est le seul autorisé ; les onglets bloqués ne
  // démarrent pas d'iframe. Demander à tous les shells n'est jamais acceptable.
  let owner = null;
  for (const client of owners) {
    if (await hasRuntime(client)) { if (owner) throw new Error('Plusieurs propriétaires'); owner = client; }
  }
  if (!owner) return new Response('Ouvrez le prototype depuis sa page d’accueil.', {status: 503});
  const channel = new MessageChannel();
  const raw = request.method === 'GET' || request.method === 'HEAD' ? new ArrayBuffer(0) : await request.arrayBuffer();
  if (raw.byteLength > 70 * 1024**2) return new Response('Envoi trop volumineux pour ce prototype (70 Mio).', {status: 413});
  const body = new Uint8Array(raw);
  return new Promise(resolve => {
    const timeout = setTimeout(() => { channel.port1.close(); resolve(new Response('Délai dépassé ; résultat incertain.', {status: 503})); }, 120000);
    channel.port1.onmessage = event => {
      clearTimeout(timeout); channel.port1.close();
      const r = event.data;
      if (!r.ok) { resolve(new Response(r.error, {status: 507})); return; }
      resolve(new Response(request.method === 'HEAD' || [204, 304].includes(r.status) ? null : r.body, {status: r.status, headers: r.headers}));
    };
    owner.postMessage({kind: 'http', request: {url: request.url, method: request.method, headers: [...request.headers], body}}, [channel.port2, raw]);
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
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/app/')) {
    event.respondWith(local(event.request).catch(() => new Response('Transport local interrompu.', {status: 503})));
  } else {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const response = await cache.match(url.pathname === '/' ? '/index.html' : url.pathname);
      return response || new Response('Ressource absente du prototype hors ligne.', {status: 404});
    })());
  }
});

// Activation explicite après arrêt du runtime par la coque propriétaire.
self.addEventListener('message', event => {
  if (event.data?.kind === 'activate-update') event.waitUntil(self.skipWaiting());
});
