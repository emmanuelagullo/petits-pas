const ESSAI = new URL(location.href).searchParams.get('essai') === 'oui';
const APERCU = new URL(location.href).searchParams.get('apercu') === 'oui';
const WORKER = './worker.js';
const BASE = new URL('./', import.meta.url).pathname;
const status = document.querySelector('#status');
const frame = document.querySelector('#app');
let worker, registration, ready = false, installPrompt;
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone;
const changement = document.querySelector('#changer-espace');
changement.textContent = ESSAI || APERCU ? 'Revenir à mon école habituelle' : 'Essayer avec l’école fictive';
changement.href = ESSAI || APERCU ? BASE : BASE + 'essai.html';
document.querySelector('#espace').textContent = APERCU ? 'Copie du ZIP à vérifier — vos modifications restent dans cette copie.' : (ESSAI ? 'Espace d’essai — utilisez des données fictives.' : 'École de ce navigateur — données conservées sur cet appareil.');
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
  document.querySelector('#network').textContent = navigator.onLine ? 'Réseau disponible' : 'Hors ligne';
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
document.querySelector('#rescue').onclick = () => document.querySelector('#recovery').click();
document.querySelector('#backup').onclick = () => {if (ready) frame.src = BASE + 'app/gestion/sauvegardes-locales/';};
document.querySelector('#apercu').onclick = () => {if (ready) frame.src = BASE + 'app/verifier-zip/';};
async function showStorage() {
  try {
    const protectedStorage = await navigator.storage.persisted();
    document.querySelector('#storage').textContent = protectedStorage
      ? 'Protection contre l’effacement automatique accordée. Une sauvegarde externe reste nécessaire.'
      : 'Protection contre l’effacement automatique non accordée. Gardez des sauvegardes hors de cet appareil.';
  } catch {document.querySelector('#storage').textContent = 'Protection du stockage impossible à vérifier.';}
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
  if (!durability?.bytes) return;
  const mib = durability.bytes / 1024**2;
  document.querySelector('#volume').textContent = `Données enregistrées : ${mib.toLocaleString('fr-FR', {maximumFractionDigits: 1})} Mio / 256 Mio (avant compression).`
    + (mib >= 205 ? ' Limite proche : téléchargez une sauvegarde et prévoyez un transfert.' : '');
}
function showUpdate() {
  const available = !!(registration?.active && registration?.waiting);
  document.querySelector('#update').hidden = !available;
  if (available) document.querySelector('#tools').open = true;
}
function rpc(message) {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = setTimeout(() => { channel.port1.close(); reject(new Error('Délai dépassé. Résultat incertain : ne répétez pas une saisie avant réouverture.')); }, 120000);
    channel.port1.onmessage = event => {
      clearTimeout(timeout); channel.port1.close();
      event.data.ok ? resolve(event.data.value) : reject(new Error(event.data.error));
    };
    worker.postMessage(message, [channel.port2, ...(message.request?.body?.buffer ? [message.request.body.buffer] : []),
      ...(message.request?.inputPort ? [message.request.inputPort] : [])]);
  });
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
  status.textContent = 'Enregistrement / lecture en cours…';
  try {
    const value = await rpc(event.data);
    showVolume(value.durability);
    if (value.durability?.bytes >= 205 * 1024**2) document.querySelector('#tools').open = true;
    status.textContent = value.result.status >= 400
      ? `Demande refusée (${value.result.status}). Les données restent sur cet appareil.`
      : 'État enregistré sur cet appareil.';
    port.postMessage({ok: true, ...value.result}, value.result.body?.buffer ? [value.result.body.buffer] : []);
    if (value.result.ouvrir_apercu) setTimeout(() => location.assign(BASE + 'apercu.html'), 0);
  } catch (error) {
    status.textContent = String(error.message);
    port.postMessage({ok: false, error: 'Opération interrompue. Fermez puis rouvrez le prototype ; ne répétez pas automatiquement cette saisie.'});
  } finally { port.close(); }
});
document.querySelector('#persist').onclick = async () => {
  try {
    await navigator.storage.persist(); await showStorage();
    status.textContent = document.querySelector('#storage').textContent;
  } catch {status.textContent = 'Protection impossible à demander. Conservez une sauvegarde hors de cet appareil.';}
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
  const recoveryWorker = new Worker(WORKER, {type: 'module'});
  try {
    if (ready && (await fetch(BASE + 'app/pwa/autoriser-recuperation/')).status !== 204) throw new Error('L’export est réservé à la direction de l’école. Connectez-vous avec ce compte.');
    status.textContent = 'Préparation du ZIP de récupération…';
    const value = await new Promise((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = setTimeout(() => {channel.port1.close(); reject(new Error('Export trop long'));}, 120000);
      channel.port1.onmessage = e => {clearTimeout(timer); channel.port1.close(); e.data.ok ? resolve(e.data.value) : reject(new Error(e.data.error));};
      recoveryWorker.postMessage({kind: 'recovery', essai: ESSAI, apercu: APERCU}, [channel.port2]);
    });
    const url = URL.createObjectURL(value.file);
    const link = document.createElement('a'); link.href = url; link.download = 'petits-pas-recuperation.zip'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status.textContent = 'ZIP de récupération téléchargé : il contient l’état conservé avant le dernier remplacement, ou l’état actuel si aucun remplacement n’a eu lieu.';
  } catch (error) {status.textContent = String(error.message);}
  finally {recoveryWorker.terminate(); event.target.disabled = false;}
};

try {
  if (!window.isSecureContext || !navigator.serviceWorker || !navigator.locks || !navigator.storage?.getDirectory) throw new Error('Navigateur incompatible : Web Locks et OPFS requis.');
  await navigator.locks.request('petits-pas-pwa-prototype' + (BASE === '/' ? '' : '-' + BASE), {ifAvailable: true}, async lock => {
    if (!lock) throw new Error('Petits Pas est déjà ouvert dans un autre onglet. Revenez à cet onglet.');
    status.textContent = 'Téléchargement et vérification de l’application pour le mode hors ligne…';
    registration = await navigator.serviceWorker.register('./sw.js', {updateViaCache: 'none'});
    showUpdate();
    registration.addEventListener('updatefound', () => {
      registration.installing?.addEventListener('statechange', showUpdate);
    });
    await controlled();
    worker = new Worker(WORKER, {type: 'module'});
    worker.addEventListener('message', event => {
      if (event.data?.kind === 'progress') status.textContent = event.data.text;
    });
    const initial = await rpc({kind: 'init', essai: ESSAI, apercu: APERCU});
    document.querySelector('#reprendre-apercu').hidden = APERCU || !initial.apercuDisponible;
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
    status.textContent = `Prêt en ${(initial.durationMs / 1000).toFixed(1)} s — ${initial.restored ? 'données retrouvées' : 'installation fictive à créer'}.`;
    frame.hidden = false;
    document.querySelector('#apercu').disabled = false;
    frame.src = BASE + 'app/';
    await new Promise(() => {}); // Possession du verrou jusqu'à fermeture du document.
  });
} catch (error) {
  worker?.terminate(); worker = null; ready = false; frame.hidden = true;
  status.textContent = String(error.message).includes('déjà ouvert') ? String(error.message) : 'Démarrage interrompu.';
  document.querySelector('#failure').hidden = false;
  document.querySelector('#tools').open = true;
  document.querySelector('#diagnostic').textContent = String(error.message);
  if (String(error.message).includes('incompatible')) document.querySelector('#failure-help').textContent = 'Ce navigateur ne fournit pas toutes les fonctions nécessaires. Essayez Chrome ou Edge récent. Le programme Windows ou Linux est une autre possibilité.';
}
