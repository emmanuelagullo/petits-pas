const BASE = new URL('./', import.meta.url).pathname;
const status = document.querySelector('#status');
const frame = document.querySelector('#app');
let worker, registration, ready = false;
function showVolume(durability) {
  if (!durability?.bytes) return;
  const mib = durability.bytes / 1024**2;
  document.querySelector('#volume').textContent = `Données enregistrées : ${mib.toLocaleString('fr-FR', {maximumFractionDigits: 1})} Mio / 64 Mio (avant compression).`
    + (mib >= 52 ? ' Limite proche : téléchargez une sauvegarde et terminez cet essai.' : '');
}
function showUpdate() { document.querySelector('#update').hidden = !registration?.waiting; }
function rpc(message) {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = setTimeout(() => { channel.port1.close(); reject(new Error('Délai dépassé. Résultat incertain : ne répétez pas une saisie avant réouverture.')); }, 120000);
    channel.port1.onmessage = event => {
      clearTimeout(timeout); channel.port1.close();
      event.data.ok ? resolve(event.data.value) : reject(new Error(event.data.error));
    };
    worker.postMessage(message, [channel.port2, ...(message.request?.body?.buffer ? [message.request.body.buffer] : [])]);
  });
}
navigator.serviceWorker.addEventListener('message', async event => {
  if (event.source === navigator.serviceWorker.controller && event.data?.kind === 'owner') {
    event.ports[0]?.postMessage(!!worker); return;
  }
  if (event.source !== navigator.serviceWorker.controller || event.data?.kind !== 'http' || !event.ports[0]) return;
  const port = event.ports[0];
  status.textContent = 'Enregistrement / lecture en cours…';
  try {
    const value = await rpc(event.data);
    showVolume(value.durability);
    status.textContent = value.result.status >= 400
      ? `Demande refusée (${value.result.status}). Les données restent sur cet appareil.`
      : 'État enregistré sur cet appareil.';
    port.postMessage({ok: true, ...value.result}, value.result.body?.buffer ? [value.result.body.buffer] : []);
  } catch (error) {
    status.textContent = String(error.message);
    port.postMessage({ok: false, error: 'Opération interrompue. Fermez puis rouvrez le prototype ; ne répétez pas automatiquement cette saisie.'});
  } finally { port.close(); }
});
document.querySelector('#persist').onclick = async () => {
  const granted = await navigator.storage.persist();
  status.textContent = granted ? 'Stockage protégé contre l’éviction automatique ; sauvegarde externe toujours nécessaire.' : 'Protection non accordée. Utilisez uniquement des données fictives.';
};
document.querySelector('#check-update').onclick = async () => {
  try {
    if (!registration) throw new Error('Installation indisponible');
    await registration.update(); showUpdate();
    status.textContent = registration.waiting ? 'Nouvelle version prête. Exportez une sauvegarde avant de l’appliquer.' : 'Vérification lancée. Une mise à jour disponible sera proposée après son téléchargement.';
  } catch { status.textContent = 'Vérification impossible hors ligne. Vous pouvez continuer à utiliser cette version.'; }
};
document.querySelector('#update').onclick = async event => {
  event.target.disabled = true;
  try {
    if (!registration?.waiting) throw new Error('Mise à jour indisponible');
    if (ready) await rpc({kind: 'checkpoint'});
    ready = false; frame.hidden = true; frame.src = 'about:blank';
    worker?.terminate(); worker = null;
    status.textContent = 'Mise à jour en cours…';
    navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), {once: true});
    registration.waiting.postMessage({kind: 'activate-update'});
  } catch (error) { status.textContent = String(error.message); event.target.disabled = false; }
};
document.querySelector('#recovery').onclick = async event => {
  event.target.disabled = true;
  const recoveryWorker = new Worker('./worker.js', {type: 'module'});
  try {
    if (ready && (await fetch(BASE + 'app/pwa/autoriser-recuperation/')).status !== 204) throw new Error('L’export est réservé à la direction de l’école. Connectez-vous avec ce compte.');
    status.textContent = 'Préparation du ZIP de récupération…';
    const value = await new Promise((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = setTimeout(() => {channel.port1.close(); reject(new Error('Export trop long'));}, 120000);
      channel.port1.onmessage = e => {clearTimeout(timer); channel.port1.close(); e.data.ok ? resolve(e.data.value) : reject(new Error(e.data.error));};
      recoveryWorker.postMessage({kind: 'recovery'}, [channel.port2]);
    });
    const url = URL.createObjectURL(new Blob([value.bytes], {type: 'application/zip'}));
    const link = document.createElement('a'); link.href = url; link.download = 'petits-pas-recuperation.zip'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status.textContent = 'ZIP de récupération téléchargé : il contient l’état conservé avant le dernier remplacement, ou l’état actuel si aucun remplacement n’a eu lieu.';
  } catch (error) {status.textContent = String(error.message);}
  finally {recoveryWorker.terminate(); event.target.disabled = false;}
};

try {
  if (!navigator.locks || !navigator.storage.getDirectory) throw new Error('Navigateur incompatible : Web Locks et OPFS requis.');
  await navigator.locks.request('petits-pas-pwa-prototype' + (BASE === '/' ? '' : '-' + BASE), {ifAvailable: true}, async lock => {
    if (!lock) throw new Error('Petits Pas est déjà ouvert dans un autre onglet. Revenez à cet onglet.');
    registration = await navigator.serviceWorker.register('./sw.js', {updateViaCache: 'none'});
    showUpdate();
    registration.addEventListener('updatefound', () => {
      registration.installing?.addEventListener('statechange', showUpdate);
    });
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
    worker = new Worker('./worker.js', {type: 'module'});
    const initial = await rpc({kind: 'init'});
    ready = true;
    showVolume(initial.durability);
    const config = await (await fetch('./config.json')).json();
    if (config.testMode) {
      window.pwaTest = rpc;
      worker.addEventListener('message', event => {
        if (event.data?.kind === 'test-checkpoint') window.pwaCheckpoint = event.data.phase;
      });
    }
    status.textContent = `Prêt en ${(initial.durationMs / 1000).toFixed(1)} s — ${initial.restored ? 'données retrouvées' : 'installation fictive à créer'}.`;
    frame.hidden = false;
    frame.src = BASE + 'app/';
    await new Promise(() => {}); // Possession du verrou jusqu'à fermeture du document.
  });
} catch (error) {
  worker?.terminate(); worker = null; ready = false; frame.hidden = true;
  status.textContent = String(error.message);
}
