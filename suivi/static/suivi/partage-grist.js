(() => {
  const invitation = document.querySelector('[data-invitation-grist]');
  if (invitation && navigator.clipboard && window.parent !== window) {
    const lien = new URL('.', window.parent.location.href);
    lien.searchParams.set('grist', invitation.dataset.invitationGrist);
    const message = invitation.querySelector('[role=status]');
    invitation.hidden = false;
    invitation.querySelector('button').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(lien.href);
        message.textContent = 'Lien d’invitation copié.';
      } catch {
        message.textContent = 'Lien d’invitation : ' + lien.href;
      }
    });
  }
  const zone = document.querySelector('[data-synchroniser-grist]');
  if (!zone) return;
  const adresse = zone.dataset.synchroniserGrist;
  const csrf = zone.querySelector('[name=csrfmiddlewaretoken]').value;
  const etat = document.querySelector('[data-etat-espace]');
  const nomEspace = document.querySelector('[data-nom-espace]');
  const relancer = document.querySelector('[data-relancer-synchro]');
  const journal = document.querySelector('[data-journal-synchro]');
  const projection = document.querySelector('[data-projection-partagee]');
  const raccordement = document.querySelector('[data-raccordement-grist][data-document-actif]');
  if (raccordement) {
    const documentGrist = url => {
      try { return new URL(url).pathname.match(/^(?:\/o\/[^/]+)?\/([^/]+)/)?.[1]; }
      catch { return undefined; }
    };
    const initial = documentGrist(raccordement.dataset.documentActif);
    const actualiser = () => {
      raccordement.querySelector('button[type=submit], button:not([type])').disabled =
        documentGrist(raccordement.elements.grist.value) === initial;
    };
    raccordement.elements.grist.addEventListener('input', actualiser);
    actualiser();
  }
  function afficher(message, enregistrer = true) {
    if (etat) etat.textContent = message;
    if (!journal || !enregistrer) return;
    const ligne = document.createElement('li');
    ligne.textContent = new Date().toLocaleString('fr-FR') + ' · ' + message;
    journal.prepend(ligne);
    if (journal.children.length > 10) journal.lastElementChild.remove();
  }

  let enCours = false;

  async function demander(url, options = {}) {
    const réponse = await fetch(url, {cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(15000), ...options});
    if (!réponse.ok) throw new Error(`HTTP ${réponse.status}`);
    return réponse.json();
  }

  const grist = (url, options) => demander(url, {credentials: 'omit', ...options});
  const json = (method, objet) => ({
    method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(objet),
  });

  async function préparer(api, table, colonnes) {
    const {tables} = await grist(api + '/tables');
    if (tables.some(t => t.id === table)) return;
    try {
      await grist(api + '/tables', json('POST', {tables: [{id: table,
        columns: colonnes.map(id => ({id, fields: {type: 'Text'}})),
      }]}));
    } catch (erreur) {
      const état = await grist(api + '/tables');
      if (!état.tables.some(t => t.id === table)) throw erreur;
    }
  }

  async function synchroniser(partage, propres) {
    const {api, table, id, nom, contenu, empreinte} = partage;
    const index = `${api}/tables/${table}/records`;
    const documents = `${api}/tables/PetitsPasContenus/records`;
    await préparer(api, table, ['Identifiant', 'Nom', 'Empreinte']);
    await préparer(api, 'PetitsPasContenus', ['Identifiant', 'Contenu']);
    await préparer(api, 'PetitsPasEspace', ['Identifiant', 'Nom']);
    const espace = api + '/tables/PetitsPasEspace/records';
    let metadata = await grist(espace);
    if (!metadata.records.some(r => r.fields.Identifiant === 'espace')) {
      await grist(espace + '?noparse=true&noupdate=true&onmany=none', json('PUT', {
        records: [{require: {Identifiant: 'espace'}, fields: {Nom: partage.nom_espace}}],
      }));
      metadata = await grist(espace);
    }
    const nomPartage = metadata.records.find(r => r.fields.Identifiant === 'espace')?.fields.Nom;
    let confirme = null;
    if (contenu !== null) {
      const écrire = (url, fields) => grist(url + '?noparse=true&onmany=none',
        json('PUT', {records: [{require: {Identifiant: id}, fields}]}));
      await écrire(documents, {Contenu: contenu});
      await écrire(index, {Nom: nom, Empreinte: empreinte});
      confirme = empreinte;
    }
    const {records} = await grist(index);
    const reçus = partage.recues;
    const autres = [...new Set(records.map(({fields}) => fields)
      .filter(f => /^[\da-f-]{36}$/i.test(f.Identifiant) && !propres.has(f.Identifiant)
        && reçus[f.Identifiant] !== f.Empreinte).map(f => f.Identifiant))];
    const lignes = [];
    for (const identifiant of autres) {
      // L’index ne contient que des métadonnées. Le contenu local n’est jamais demandé.
      const filtre = encodeURIComponent(JSON.stringify({Identifiant: [identifiant]}));
      const réponse = await grist(`${documents}?filter=${filtre}`);
      if (réponse.records.length === 1) lignes.push(réponse.records[0].fields);
    }
    const opérations = json('POST', {id, api, lignes, nom: nomPartage || partage.nom_espace, confirme});
    opérations.headers['X-CSRFToken'] = csrf;
    return demander(adresse, opérations);
  }

  async function synchroniserÉquipe(partage) {
    const transfert = partage.transfert_equipe;
    const table = 'PetitsPasContributions';
    const index = `${partage.api}/tables/${table}/records`;
    const {connues, a_envoyer} = await demander(transfert);
    const {tables} = await grist(partage.api + '/tables');
    if (!a_envoyer.length && !tables.some(t => t.id === table)) return;
    if (!tables.some(t => t.id === table)) await préparer(partage.api, table, ['Empreinte', 'Edition']);
    const transmettre = ligne => {
      const options = json('POST', ligne);
      options.headers['X-CSRFToken'] = csrf;
      return demander(transfert, options);
    };
    if (a_envoyer.length) {
      const ligne = a_envoyer[0];
      await grist(index + '?noparse=true&noupdate=true&onmany=none',
        json('PUT', {records: [{require: {Empreinte: ligne.empreinte},
          fields: {Edition: JSON.stringify(ligne.edition)}}]}));
    }
    const {records} = await grist(index);
    const acquittées = new Set(connues);
    for (const {fields} of records) {
      if (acquittées.has(fields.Empreinte) && fields.Empreinte !== a_envoyer[0]?.empreinte) continue;
      await transmettre({empreinte: fields.Empreinte, edition: JSON.parse(fields.Edition)});
    }
  }

  async function vérifier() {
    if (enCours) return;
    if (!navigator.onLine) {
      afficher('Hors ligne. La synchronisation reprendra à la reconnexion.', false);
      return;
    }
    enCours = true;
    if (relancer) relancer.disabled = true;
    afficher('Synchronisation en cours…', false);
    try {
      const {partages, propres} = await demander(adresse);
      for (const partage of partages) {
        const affiché = nomEspace?.dataset.partage === partage.id;
        try {
          const résultat = await synchroniser(partage, new Set(propres));
          if (affiché && projection && résultat.partage_confirme && !partage.erreur)
            projection.textContent = 'Votre référentiel a été partagé dans cet espace.';
          await synchroniserÉquipe(partage);
          if (affiché && résultat.nom) nomEspace.textContent = résultat.nom;
          if (affiché) afficher(partage.erreur || (résultat.erreurs
            ? 'Des référentiels reçus sont illisibles.' : 'Synchronisation terminée.'));
        } catch {
          if (affiché) afficher('Synchronisation incomplète. Réessayez quand le document est accessible.');
        }
      }
    } catch {
      afficher('Synchronisation en attente. Réessayez à la reconnexion.');
    } finally {
      enCours = false;
      if (relancer) relancer.disabled = false;
    }
  }

  function lancer() {
    if (navigator.locks) {
      navigator.locks.request('petits-pas-grist:' + adresse, {ifAvailable: true},
        verrou => verrou ? vérifier() : undefined).catch(() => {});
    } else {
      vérifier();
    }
  }
  if (relancer) { relancer.hidden = false; relancer.addEventListener('click', lancer); }
  addEventListener('online', lancer);
  if (!document.hidden) lancer();
  setInterval(() => { if (!document.hidden) lancer(); }, 60000);
})();
