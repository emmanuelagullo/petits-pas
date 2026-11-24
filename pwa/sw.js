const BASE = new URL('./', self.location.href).pathname;
const assetURL = path => BASE + path.replace(/^\//, '');
const CACHE_PREFIX = 'petits-pas-pwa-' + BASE;
const VERSION = '__BUILD__';
const CACHE = CACHE_PREFIX + VERSION;

async function matchesAsset(response, asset) {
  if (!response?.ok) return false;
  const bytes = await response.clone().arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  return hash === asset.sha256;
}

async function installVersion() {
  const manifest = await fetch(assetURL('/config.json'), {cache: 'no-store'});
  if (!manifest.ok) throw new Error('Manifeste indisponible');
  const config = await manifest.json();
  if (config.version !== VERSION) throw new Error('Version du manifeste différente du service worker');
  const cache = await caches.open(CACHE);
  const previous = (await caches.keys()).reverse().filter(name =>
    // Le préfixe comprend la portée. Le suffixe ne doit pas être un sous-chemin.
    name.startsWith(CACHE_PREFIX) && !name.slice(CACHE_PREFIX.length).includes('/') && name !== CACHE
  );
  let checked = 0;
  const progress = async () => {
    try {
      // Le service worker en cours d’installation ne contrôle pas encore ces fenêtres.
      const windows = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
      for (const client of windows) {
        if ([BASE, BASE + 'index.html'].includes(new URL(client.url).pathname)) {
          client.postMessage({kind: 'update-progress', checked, total: config.assets.length});
        }
      }
    } catch {
      // Un onglet peut se fermer pendant l’installation.
    }
  };
  await progress();
  for (const asset of config.assets) {
    const url = assetURL(asset.url);
    const partial = await cache.match(url);
    if (!await matchesAsset(partial, asset)) {
      let reusable;
      for (const name of previous) {
        const candidate = await caches.match(url, {cacheName: name});
        if (await matchesAsset(candidate, asset)) {
          reusable = candidate;
          break;
        }
      }
      if (!reusable) {
        reusable = await fetch(url, {cache: 'no-store'});
        if (!reusable.ok) throw new Error('Fichier absent : ' + asset.url);
        if (!await matchesAsset(reusable, asset)) throw new Error('Empreinte incorrecte : ' + asset.url);
      }
      await cache.put(url, reusable);
    }
    checked++;
    await progress();
  }
  await cache.put(assetURL('/config.json'), new Response(JSON.stringify(config), {headers: {'Content-Type': 'application/json'}}));
}

self.addEventListener('install', event => event.waitUntil(installVersion().catch(error => {
  console.error('Installation de Petits Pas interrompue', error);
  throw error;
})));
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
  const multipart = request.method === 'POST' && request.headers.get('content-type')?.startsWith('multipart/form-data');
  const stream = multipart ? request.body : null;
  const upload = typeof stream?.getReader === 'function' ? new MessageChannel() : null;
  const limit = 70 * 1024**2;
  let raw = new ArrayBuffer(0);
  if (!upload && request.method !== 'GET' && request.method !== 'HEAD') {
    try {
      if (multipart) {
        // Certains navigateurs savent lire le corps sans exposer son flux.
        const payload = await request.blob();
        if (payload.size > limit) return new Response('Envoi trop volumineux (70 Mio sans transfert progressif).', {status: 413});
        raw = await payload.arrayBuffer();
      } else {
        raw = await request.arrayBuffer();
      }
    } catch {
      return new Response('Le navigateur n’a pas pu lire le formulaire. La demande n’a pas été transmise à Petits Pas.', {status: 503});
    }
  }
  if (raw.byteLength > limit) return new Response('Envoi trop volumineux (70 Mio).', {status: 413});
  const channel = new MessageChannel();
  const body = new Uint8Array(raw);
  let uploadReader;
  const stopUpload = () => {
    uploadReader?.cancel().catch(() => {});
    upload.port1.close();
  };
  if (upload) {
    // Une tranche est envoyée seulement après consommation de la précédente.
    const reader = uploadReader = stream.getReader();
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
    let terminé = false;
    function terminer() {
      if (terminé) return false;
      terminé = true;
      clearTimeout(timeout);
      clearInterval(surveillance);
      request.signal.removeEventListener('abort', interrompre);
      if (upload) stopUpload();
      channel.port1.close();
      return true;
    }
    function interrompre() {
      if (terminer()) resolve(new Response(
        'Transport interrompu ; résultat incertain. Fermez puis rouvrez Petits Pas.', {status: 503}));
    }
    const timeout = setTimeout(interrompre, 16 * 60 * 1000);
    // Une fermeture du propriétaire peut laisser le port sans réponse et
    // retenir l’ancien service worker, même si le navigateur ne signale pas
    // l’annulation de la requête.
    const surveillance = setInterval(() => {
      self.clients.get(owner.id).then(client => { if (!client) interrompre(); }, () => {});
    }, 2000);
    request.signal.addEventListener('abort', interrompre, {once: true});
    if (request.signal.aborted) { interrompre(); return; }
    channel.port1.onmessage = event => {
      if (!terminer()) return;
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
    try { owner.postMessage({kind: 'http', request: {url: request.url, method: request.method, headers, body,
      ...(upload ? {inputPort:upload.port2} : {})}}, [channel.port2, raw, ...(upload ? [upload.port2] : [])]);
    } catch { interrompre(); }
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
