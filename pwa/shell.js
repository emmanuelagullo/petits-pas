import {requestWorker} from './transport.js';
const ESSAI = new URL(location.href).searchParams.get('essai') === 'oui';
const APERCU = new URL(location.href).searchParams.get('apercu') === 'oui';
const WORKER = './worker.js';
const BASE = new URL('./', import.meta.url).pathname;
const status = document.querySelector('#status');
const frame = document.querySelector('#app');
let worker, registration, ready = false, installPrompt;
let applyingUpdate = false;
const pendingHttp = new Set();
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone;
const changement = document.querySelector('#changer-espace');
changement.hidden = ESSAI || APERCU;
const espace = document.querySelector('#espace');
espace.hidden = !(ESSAI || APERCU);
espace.textContent = APERCU ? 'Copie de sauvegarde' : 'École fictive';
const retourEcole = document.querySelector('#retour-ecole');
retourEcole.hidden = espace.hidden;
retourEcole.href = BASE;
const tools = document.querySelector('#tools');
document.querySelector('#storage-tools').onclick = () => {
  tools.open = true;
  document.querySelector('#titre-stockage').focus();
};
document.querySelector('#apercu').hidden = APERCU;
if (ESSAI && !APERCU) {
  fetch('./ecole-fictive.json').then(response => response.json()).then(notice => {
    const comptes = document.querySelector('#comptes-essai');
    comptes.textContent = 'Comptes publics — enseignant : ' + notice.identifiants.enseignant.utilisateur +
      ' / ' + notice.identifiants.enseignant.mot_de_passe + '; direction : ' + notice.identifiants.direction.utilisateur +
      ' / ' + notice.identifiants.direction.mot_de_passe;
    comptes.hidden = false;
  }).catch(() => {});
}
function showNetwork() {
  const network = document.querySelector('#network');
  network.textContent = 'Hors ligne';
  network.hidden = navigator.onLine;
}
showNetwork();
window.addEventListener('online', showNetwork);
window.addEventListener('offline', showNetwork);
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); installPrompt = event;
  document.querySelector('#install').hidden = standalone();
});
window.addEventListener('appinstalled', () => {
  installPrompt = null; document.querySelector('#install').hidden = true;
  document.querySelector('#installation').textContent = 'Petits Pas est installé. Retrouvez-le depuis son icône.';
});
document.querySelector('#install').onclick = async () => {
  if (!installPrompt) return;
  try {
    await installPrompt.prompt(); await installPrompt.userChoice;
    installPrompt = null; document.querySelector('#install').hidden = true;
  } catch {status.textContent = 'Installation indisponible. Utilisez le menu du navigateur ou cette page.';}
};
if (standalone()) document.querySelector('#installation').textContent = 'Petits Pas est ouvert depuis son icône.';
document.querySelector('#retry').onclick = () => location.reload();
document.querySelector('#backup').onclick = () => {if (ready) frame.src = BASE + 'app/gestion/sauvegardes-locales/';};
document.querySelector('#apercu').onclick = () => {if (ready) frame.src = BASE + 'app/verifier-zip/';};
const storage = document.querySelector('#storage');
const persist = document.querySelector('#persist');
async function showStorage() {
  try {
    const protection = await navigator.storage.persisted();
    storage.textContent = protection
      ? 'Protection contre l’effacement automatique accordée.'
      : 'Protection contre l’effacement automatique non accordée.';
    persist.hidden = protection || typeof navigator.storage.persist !== 'function';
  } catch {
    storage.textContent = 'Protection du stockage impossible à vérifier.';
  }
}
void showStorage();
function controlled() {
  if (navigator.serviceWorker.controller?.scriptURL === new URL('./sw.js', location.href).href) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error('Installation trop longue. Vérifiez la connexion puis réessayez.')), 120000);
    function finish(error) {
      clearTimeout(timer); navigator.serviceWorker.removeEventListener('controllerchange', check);
      registration.removeEventListener('updatefound', watch);
      error ? reject(error) : resolve();
    }
    function check() {
      if (navigator.serviceWorker.controller?.scriptURL === new URL('./sw.js', location.href).href) finish();
    }
    function watch() {
      const installing = registration.installing;
      installing?.addEventListener('statechange', () => {
        if (installing.state === 'redundant' && !registration.active) finish(new Error('Téléchargement incomplet. Vérifiez la connexion puis réessayez.'));
        check();
      });
    }
    navigator.serviceWorker.addEventListener('controllerchange', check);
    registration.addEventListener('updatefound', watch); watch(); check();
  });
}
function showVolume(durability) {
  const nearLimit = durability?.bytes >= 205 * 1024**2;
  document.querySelector('#storage-warning').hidden = !nearLimit;
  document.querySelector('#storage-tools').hidden = !nearLimit;
  if (!Number.isFinite(durability?.bytes)) return;
  const mib = durability.bytes / 1024**2;
  document.querySelector('#volume').textContent = `Données enregistrées : ${mib.toLocaleString('fr-FR', {maximumFractionDigits: 1})} Mio / 256 Mio.`;
}
const checkUpdate = document.querySelector('#check-update');
const updateStatus = document.querySelector('#update-status');
const updateCheckStatus = document.querySelector('#update-check-status');
function showUpdateStatus(message, dansOutils = false) {
  updateCheckStatus.textContent = dansOutils ? message : '';
  updateStatus.textContent = dansOutils ? '' : message;
}
const updateProgress = document.querySelector('#update-progress');
const updateRetry = document.querySelector('#update-retry');
const resumeLabel = 'Reprendre le téléchargement';
let installingUpdate;

function showUpdate() {
  const available = !!(registration?.active && registration?.waiting);
  document.querySelector('#update').hidden = !available;
  if (available) {
    updateRetry.hidden = true;
    updateProgress.hidden = true;
    showUpdateStatus('Nouvelle version prête à appliquer.');
    checkUpdate.textContent = 'Vérifier les mises à jour';
  }
  return available;
}

function watchUpdate() {
  const candidate = registration.installing;
  if (!registration.active || !candidate || installingUpdate === candidate) return;
  installingUpdate = candidate;
  checkUpdate.disabled = true;
  updateRetry.hidden = true;
  updateProgress.removeAttribute('value');
  updateProgress.hidden = false;
  showUpdateStatus('Téléchargement et vérification de la mise à jour…');
  function stateChanged() {
    if (installingUpdate !== candidate) return;
    if (candidate.state === 'redundant') {
      const count = updateProgress.hasAttribute('value')
        ? ` (${updateProgress.value} ressources vérifiées sur ${updateProgress.max})`
        : '';
      showUpdateStatus(`Installation de la mise à jour interrompue${count}. Vous pouvez reprendre le téléchargement.`);
      updateRetry.textContent = resumeLabel;
      updateRetry.hidden = false;
    } else if (!showUpdate() && candidate.state !== 'activated') {
      return;
    }
    installingUpdate = null;
    updateProgress.hidden = true;
    checkUpdate.disabled = false;
    candidate.removeEventListener('statechange', stateChanged);
  }
  candidate.addEventListener('statechange', stateChanged);
  stateChanged();
}

navigator.serviceWorker?.addEventListener('message', event => {
  if (event.data?.kind !== 'update-progress' || event.source !== registration?.installing) return;
  watchUpdate();
  if (event.source !== installingUpdate) return;
  const {checked, total} = event.data;
  updateProgress.max = total;
  updateProgress.value = checked;
  showUpdateStatus(`${checked} ressources vérifiées sur ${total}.`);
});

function stopRuntime() {
  worker?.terminate(); worker = null; ready = false;
  frame.hidden = true;
  document.querySelector('#backup').disabled = true;
  document.querySelector('#apercu').disabled = true;
  document.querySelector('#failure').hidden = false;
  document.querySelector('#diagnostic').textContent = 'Délai dépassé : le moteur a été arrêté. Rouvrez pour vérifier le dernier état confirmé.';
}
function rpc(message) {
  if (!worker) return Promise.reject(new Error('Moteur arrêté. Fermez puis rouvrez Petits Pas.'));
  return requestWorker(worker, message, {onTimeout: stopRuntime});
}

navigator.serviceWorker?.addEventListener('message', async event => {
  if (event.source === navigator.serviceWorker.controller && event.data?.kind === 'release-export') {
    if (worker) await rpc(event.data).catch(()=>{}); return;
  }
  if (event.source === navigator.serviceWorker.controller && event.data?.kind === 'owner') {
    event.ports[0]?.postMessage(!!worker); return;
  }
  if (event.source !== navigator.serviceWorker.controller || event.data?.kind !== 'http' || !event.ports[0]) return;
  const port = event.ports[0];
  if (applyingUpdate) {
    port.postMessage({ok: true, status: 503, headers: [], body: new TextEncoder().encode('Mise à jour en cours.')});
    port.close();
    return;
  }
  const operation = rpc(event.data);
  pendingHttp.add(operation);
  const started = performance.now();
  const waiting = setInterval(() => {
    status.textContent = `Opération en cours depuis ${Math.floor((performance.now() - started) / 1000)} s. Gardez cette page ouverte ; les gros ZIP peuvent prendre plusieurs minutes.`;
  }, 5000);
  try {
    const value = await operation;
    showVolume(value.durability);
    status.textContent = value.result.status >= 400
      ? `Demande refusée (${value.result.status}). Les données restent sur cet appareil.`
      : '';
    port.postMessage({ok: true, ...value.result}, value.result.body?.buffer ? [value.result.body.buffer] : []);
    if (value.result.ouvrir_apercu) setTimeout(() => location.assign(BASE + 'apercu.html'), 0);
  } catch (error) {
    status.textContent = String(error.message);
    port.postMessage({ok: false, error: 'Opération interrompue. Fermez puis rouvrez Petits Pas ; ne répétez pas automatiquement cette saisie.'});
  } finally { pendingHttp.delete(operation); clearInterval(waiting); port.close(); }
});
persist.onclick = async () => {
  persist.disabled = true;
  try {
    await navigator.storage.persist();
    await showStorage();
    if (persist.hidden) storage.focus();
  } catch {
    storage.textContent = 'Protection impossible à demander.';
  } finally {
    persist.disabled = false;
  }
};
checkUpdate.onclick = async () => {
  if (!registration || showUpdate()) return;
  checkUpdate.disabled = true;
  updateRetry.hidden = true;
  showUpdateStatus('Recherche d’une mise à jour…', true);
  try {
    await registration.update();
    watchUpdate();
    if (!installingUpdate && !showUpdate() && updateRetry.hidden) {
      showUpdateStatus('Aucune nouvelle version détectée.', true);
    }
  } catch {
    showUpdateStatus('La vérification a échoué. Vérifiez la connexion, puis réessayez.');
    updateRetry.textContent = 'Réessayer la vérification';
    updateRetry.hidden = false;
  } finally {
    checkUpdate.disabled = !!installingUpdate;
  }
};
updateRetry.onclick = checkUpdate.onclick;
document.querySelector('#update').onclick = async event => {
  event.target.disabled = true;
  try {
    const candidate = registration?.waiting;
    if (!candidate) throw new Error('Mise à jour indisponible');
    // Fermer l’admission avant le checkpoint : une requête d’arrière-plan
    // abandonnée au moment d’arrêter le moteur retient l’ancien service worker.
    applyingUpdate = true;
    await Promise.allSettled(pendingHttp);
    if (ready) await rpc({kind: 'checkpoint'});
    ready = false; frame.hidden = true; frame.src = 'about:blank';
    worker?.terminate(); worker = null;
    status.textContent = 'Mise à jour en cours…';
    navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), {once: true});
    candidate.postMessage({kind: 'activate-update'});
  } catch (error) {
    applyingUpdate = false;
    status.textContent = String(error.message);
    event.target.disabled = false;
  }
};
const boutonsRecuperation = document.querySelectorAll('#recovery, #rescue');
async function exporterRecuperation(etat) {
  boutonsRecuperation.forEach(bouton => { bouton.disabled = true; });
  etat.textContent = 'Préparation du ZIP de récupération…';
  let recoveryWorker;
  try {
    if (ready && (await fetch(BASE + 'app/pwa/autoriser-recuperation/')).status !== 204) throw new Error('L’export est réservé à la direction de l’école. Connectez-vous avec ce compte.');
    recoveryWorker = new Worker(WORKER, {type: 'module'});
    const value = await requestWorker(recoveryWorker, {kind: 'recovery', essai: ESSAI, apercu: APERCU}, {onTimeout: () => recoveryWorker.terminate()});
    const url = URL.createObjectURL(value.file);
    const link = document.createElement('a'); link.href = url; link.download = 'petits-pas-recuperation.zip'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    etat.textContent = 'Téléchargement du ZIP de récupération lancé.';
  } catch (error) {
    etat.textContent = String(error.message);
  } finally {
    recoveryWorker?.terminate();
    boutonsRecuperation.forEach(bouton => { bouton.disabled = false; });
  }
}

for (const bouton of boutonsRecuperation) {
  const etat = document.getElementById(bouton.id + '-status');
  bouton.onclick = () => exporterRecuperation(etat);
}

const navigateurCompatible = window.isSecureContext && navigator.serviceWorker
  && navigator.locks && navigator.storage?.getDirectory;
try {
  if (!navigateurCompatible) throw new Error('Navigateur incompatible : Web Locks et OPFS requis.');
  await navigator.locks.request('petits-pas-pwa-prototype' + (BASE === '/' ? '' : '-' + BASE), {ifAvailable: true}, async lock => {
    if (!lock) throw new Error('Petits Pas est déjà ouvert dans un autre onglet. Revenez à cet onglet.');
    status.textContent = 'Téléchargement et vérification de l’application pour le mode hors ligne…';
    registration = await navigator.serviceWorker.register('./sw.js', {updateViaCache: 'none'});
    showUpdate();
    registration.addEventListener('updatefound', watchUpdate);
    watchUpdate();
    await controlled();
    worker = new Worker(WORKER, {type: 'module'});
    worker.addEventListener('message', event => {
      if (event.data?.kind === 'progress') status.textContent = event.data.text;
    });
    const initial = await rpc({kind: 'init', essai: ESSAI, apercu: APERCU});
    document.querySelector('#copie-disponible').hidden = APERCU || !initial.apercuDisponible;
    ready = true;
    showVolume(initial.durability);
    const config = await (await fetch('./config.json')).json();
    document.querySelector('#version').textContent = 'Version ' + (config.application_version || config.version);
    document.querySelector('#details-version').textContent = config.version + ' — ' + (config.commit || '');
    document.querySelector('#nouveautes').href = './nouveautes.html';
    document.querySelector('#backup').disabled = false;
    if (config.testMode) {
      window.pwaTest = rpc;
      worker.addEventListener('message', event => {
        if (event.data?.kind === 'test-checkpoint') window.pwaCheckpoint = event.data.phase;
      });
    }
    status.textContent = '';
    frame.hidden = false;
    document.querySelector('#apercu').disabled = false;
    frame.src = BASE + 'app/';
    await new Promise(() => {}); // Possession du verrou jusqu'à fermeture du document.
  });
} catch (error) {
  worker?.terminate(); worker = null; ready = false; frame.hidden = true;
  status.textContent = String(error.message).includes('déjà ouvert') ? String(error.message) : 'Démarrage interrompu.';
  document.querySelector('#failure').hidden = false;
  document.querySelector('#diagnostic').textContent = String(error.message);
  const aide = document.querySelector('#failure-help');
  if (!navigateurCompatible) {
    aide.textContent = 'Ce navigateur ne fournit pas toutes les fonctions nécessaires. Essayez Chrome ou Edge récent. Le programme Windows ou Linux est une autre possibilité.';
  } else if (String(error.message).includes("Base issue d'une version plus récente ou incompatible.")) {
    aide.textContent = 'Cette version de Petits Pas ne peut pas ouvrir les données enregistrées. Utilisez « Récupérer un ZIP » pour télécharger une copie de récupération. Ne supprimez pas les données du site.';
  }
}
