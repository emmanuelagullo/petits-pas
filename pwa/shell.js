const status = document.querySelector('#status');
const frame = document.querySelector('#app');
let worker;
function rpc(message) {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = setTimeout(() => { channel.port1.close(); reject(new Error('Délai dépassé. Résultat incertain : ne répétez pas une saisie avant réouverture.')); }, 120000);
    channel.port1.onmessage = event => {
      clearTimeout(timeout); channel.port1.close();
      event.data.ok ? resolve(event.data.value) : reject(new Error(event.data.error));
    };
    worker.postMessage(message, [channel.port2]);
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
    status.textContent = value.result.status >= 400
      ? `Demande refusée (${value.result.status}). Les données restent sur cet appareil.`
      : 'État enregistré sur cet appareil.';
    port.postMessage({ok: true, ...value.result});
  } catch (error) {
    status.textContent = String(error.message);
    port.postMessage({ok: false, error: 'Opération interrompue. Fermez puis rouvrez le prototype ; ne répétez pas automatiquement cette saisie.'});
  } finally { port.close(); }
});
document.querySelector('#persist').onclick = async () => {
  const granted = await navigator.storage.persist();
  status.textContent = granted ? 'Stockage protégé contre l’éviction automatique ; sauvegarde externe toujours nécessaire.' : 'Protection non accordée. Utilisez uniquement des données fictives.';
};
try {
  if (!navigator.locks || !navigator.storage.getDirectory) throw new Error('Navigateur incompatible : Web Locks et OPFS requis.');
  await navigator.locks.request('petits-pas-pwa-prototype', {ifAvailable: true}, async lock => {
    if (!lock) throw new Error('Petits Pas est déjà ouvert dans un autre onglet. Revenez à cet onglet.');
    await navigator.serviceWorker.register('./sw.js');
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once: true}));
    worker = new Worker('./worker.js', {type: 'module'});
    const initial = await rpc({kind: 'init'});
    const config = await (await fetch('./config.json')).json();
    if (config.testMode) window.pwaTest = rpc;
    status.textContent = `Prêt en ${(initial.durationMs / 1000).toFixed(1)} s — ${initial.restored ? 'données retrouvées' : 'installation fictive à créer'}.`;
    frame.hidden = false;
    frame.src = '/app/';
    await new Promise(() => {}); // Possession du verrou jusqu'à fermeture du document.
  });
} catch (error) { status.textContent = String(error.message); }
