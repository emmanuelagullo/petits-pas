(() => {
  const zone = document.querySelector('[data-synchroniser-grist]');
  if (!zone) return;
  const adresse = zone.dataset.synchroniserGrist;
  const csrf = zone.querySelector('[name=csrfmiddlewaretoken]').value;
  const etat = document.querySelector('[data-etat-espace]');
  const nomEspace = document.querySelector('[data-nom-espace]');
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
    const document = await grist(api);
    await préparer(api, table, ['Identifiant', 'Nom', 'Empreinte']);
    await préparer(api, 'PetitsPasContenus', ['Identifiant', 'Contenu']);
    await préparer(api, 'PetitsPasEspace', ['Identifiant', 'Nom']);
    const espace = api + '/tables/PetitsPasEspace/records';
    let metadata = await grist(espace);
    if (!metadata.records.some(r => r.fields.Identifiant === 'espace')) {
      await grist(espace + '?noparse=true&noupdate=true&onmany=none', json('PUT', {
        records: [{require: {Identifiant: 'espace'}, fields: {Nom: document.name}}],
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
    const opérations = json('POST', {id, api, lignes, nom: nomPartage || document.name, confirme});
    opérations.headers['X-CSRFToken'] = csrf;
    return demander(adresse, opérations);
  }

  async function vérifier() {
    if (enCours || !navigator.onLine) return;
    enCours = true;
    try {
      const {partages, propres} = await demander(adresse);
      for (const partage of partages) {
        const affiché = nomEspace?.dataset.partage === partage.id;
        try {
          const résultat = await synchroniser(partage, new Set(propres));
          if (affiché && résultat.nom) nomEspace.textContent = résultat.nom;
          if (affiché && etat) etat.textContent = partage.erreur || (résultat.erreurs
            ? 'Des référentiels reçus sont illisibles.' : 'Synchronisation terminée.');
        } catch {
          if (affiché && etat) etat.textContent = 'Synchronisation en attente. Réessai automatique à la reconnexion.';
        }
      }
    } catch {
      if (etat) etat.textContent = 'Synchronisation en attente. Nouvel essai au retour du réseau ou à la prochaine ouverture.';
    } finally {
      enCours = false;
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
  addEventListener('online', lancer);
  if (!document.hidden) lancer();
  setInterval(() => { if (!document.hidden) lancer(); }, 60000);
})();
