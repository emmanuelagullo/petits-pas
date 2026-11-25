(() => {
  const invitation = document.querySelector('[data-invitation-grist]');
  if (invitation && navigator.clipboard && window.parent !== window) {
    const lien = new URL('.', window.parent.location.href);
    lien.searchParams.set('grist', invitation.dataset.invitationGrist);
    if (invitation.dataset.usageGrist) lien.searchParams.set('usage', invitation.dataset.usageGrist);
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
  const adresse = zone?.dataset.synchroniserGrist;
  const csrf = zone?.querySelector('[name=csrfmiddlewaretoken]').value;
  const etat = document.querySelector('[data-etat-espace]');
  const nomEspace = document.querySelector('[data-nom-espace]');
  const relancer = document.querySelector('[data-relancer-synchro]');
  const réception = document.querySelector('[data-reception-espace]');
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
      const bouton = raccordement.querySelector('[value="raccorder"]');
      const destination = documentGrist(raccordement.elements.grist.value);
      bouton.disabled = destination === initial;
      bouton.classList.toggle('avertissement-orange', Boolean(destination && destination !== initial));
      bouton.textContent = destination && destination !== initial
        ? 'Confirmer le changement d’espace' : 'Confirmer le raccordement';
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
        columns: colonnes.map(id => ({id, fields: {type: id === 'Numero' ? 'Int' : 'Text'}})),
      }]}));
    } catch (erreur) {
      const état = await grist(api + '/tables');
      if (!état.tables.some(t => t.id === table)) throw erreur;
    }
  }

  const cheminIcônes = '/tables/PetitsPasIcones/records';
  const filtreIcône = empreinte => '?filter=' + encodeURIComponent(JSON.stringify({Empreinte: [empreinte]}));

  async function publierIcônes(api, icônes) {
    if (!Object.keys(icônes).length) return;
    await préparer(api, 'PetitsPasIcones', ['Empreinte', 'PNG']);
    for (const [empreinte, png] of Object.entries(icônes)) {
      const chemin = api + cheminIcônes;
      const {records} = await grist(chemin + filtreIcône(empreinte));
      if (records.length === 1 && records[0].fields.PNG === png) continue;
      if (records.length) throw new Error('Icône incohérente');
      await grist(chemin + '?noparse=true&noupdate=true&onmany=none', json('PUT', {
        records: [{require: {Empreinte: empreinte}, fields: {PNG: png}}],
      }));
      const après = await grist(chemin + filtreIcône(empreinte));
      if (après.records.length !== 1 || après.records[0].fields.PNG !== png)
        throw new Error('Icône non confirmée');
    }
  }

  const retrait = document.querySelector('[data-retrait-grist]');
  if (retrait && adresse && navigator.locks) {
    retrait.hidden = false;
    const formulaire = retrait.querySelector('form');
    const bouton = formulaire.querySelector('button');
    const état = formulaire.querySelector('[role=status]');
    formulaire.addEventListener('submit', async event => {
      event.preventDefault();
      bouton.disabled = true;
      état.textContent = 'Retrait en cours…';
      try {
        await navigator.locks.request('petits-pas-grist:' + adresse, async () => {
          const réponse = await fetch(location.href, {
            method: 'POST', body: new FormData(formulaire), signal: AbortSignal.timeout(15000),
          });
          if (!réponse.ok) throw new Error('Préparation refusée');
          const {api, identifiant} = await réponse.json();
          const {tables} = await grist(api + '/tables');
          const filtre = encodeURIComponent(JSON.stringify({Identifiant: [identifiant]}));
          const actions = [];
          const chemins = [];
          for (const table of ['PetitsPasClasses', 'PetitsPasContenus']) {
            if (!tables.some(t => t.id === table)) continue;
            const chemin = api + `/tables/${table}/records?filter=${filtre}`;
            chemins.push(chemin);
            const {records} = await grist(chemin);
            for (const ligne of records) {
              if (ligne.fields.Identifiant === identifiant) actions.push(['RemoveRecord', table, ligne.id]);
            }
          }
          if (actions.length) await grist(api + '/apply', json('POST', actions));
          for (const chemin of chemins) {
            const {records} = await grist(chemin);
            if (records.length) throw new Error('Retrait non confirmé');
          }
        });
        état.textContent = 'Référentiel retiré. Synchronisation suspendue.';
        if (relancer) relancer.hidden = true;
        if (projection) projection.textContent = 'Référentiel retiré de cet espace.';
        if (etat) etat.textContent = 'Synchronisation suspendue.';
      } catch {
        état.textContent = 'Retrait non confirmé. Vérifiez l’accès au document et réessayez.';
      } finally {
        bouton.disabled = false;
      }
    });
  }

  const publication = document.querySelector('[data-publier-equipe-grist]');
  if (publication) {
    publication.hidden = false;
    const bouton = publication.querySelector('button');
    const état = publication.querySelector('[role=status]');
    publication.addEventListener('submit', async event => {
      event.preventDefault();
      if (bouton.disabled) return;
      bouton.disabled = true;
      état.textContent = 'Publication en cours…';
      try {
        const réponse = await fetch(window.location.href, {
          method: 'POST', body: new FormData(publication), signal: AbortSignal.timeout(15000),
        });
        const {api, reference, titre, contenu, icones, erreur} = await réponse.json();
        if (!réponse.ok) {
          état.textContent = erreur || 'Impossible de préparer cette édition.';
          return;
        }
        await publierIcônes(api, icones);
        const chemin = api + '/tables/Editions/records';
        await préparer(api, 'Editions', ['Numero', 'Referentiel', 'Titre', 'Contenu']);
        const {columns} = await grist(api + '/tables/Editions/columns');
        const types = Object.fromEntries(columns.map(({id, fields}) => [id, fields.type]));
        if (!['Int', 'Numeric'].includes(types.Numero) ||
            ['Referentiel', 'Titre', 'Contenu'].some(nom => types[nom] !== 'Text')) {
          état.textContent = 'La table des éditions de ce catalogue est incompatible.';
          return;
        }
        const {records} = await grist(chemin);
        const lignes = records.map(ligne => ligne.fields);
        const éditions = lignes.filter(ligne => ligne.Referentiel === reference);
        const dernière = éditions.reduce((maximum, ligne) =>
          ligne.Numero > (maximum?.Numero || 0) ? ligne : maximum, null);
        if (dernière?.Contenu === contenu) {
          état.textContent = `Édition ${dernière.Numero} déjà proposée au suivi.`;
          return;
        }
        const globale = lignes.some(ligne => !ligne.Contenu);
        const numéro = 1 + Math.max(0, ...(globale ? lignes : éditions).map(ligne => ligne.Numero));
        const cle = globale ? {Numero: numéro} : {Numero: numéro, Referentiel: reference};
        const champs = {Numero: numéro, Referentiel: reference, Titre: dernière?.Titre || titre, Contenu: contenu};
        try {
          await grist(chemin + '?noparse=true&noupdate=true&onmany=none', json('PUT', {
            records: [{require: cle, fields: champs}],
          }));
        } catch {
          // Une réponse perdue n’empêche pas de relire l’écriture.
        }
        const après = await grist(chemin);
        const correspondances = après.records.filter(({fields}) =>
          Object.entries(cle).every(([nom, valeur]) => fields[nom] === valeur));
        if (correspondances.length !== 1 || !Object.entries(champs).every(
          ([nom, valeur]) => correspondances[0].fields[nom] === valeur)) {
          throw new Error('Édition non confirmée');
        }
        état.textContent = `Édition ${numéro} proposée au suivi dans le catalogue de l’espace.`;
      } catch {
        état.textContent = 'Publication non confirmée. Vérifiez l’accès en écriture au document puis réessayez.';
      } finally {
        bouton.disabled = false;
      }
    });
  }
  if (!zone) return;

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
      await publierIcônes(api, partage.icones);
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
    const icônesLues = new Map();
    for (const identifiant of autres) {
      // L’index ne contient que des métadonnées. Le contenu local n’est jamais demandé.
      const filtre = encodeURIComponent(JSON.stringify({Identifiant: [identifiant]}));
      const réponse = await grist(`${documents}?filter=${filtre}`);
      if (réponse.records.length !== 1) continue;
      const champs = réponse.records[0].fields;
      const icones = {};
      for (const [, empreinte] of String(champs.Contenu ?? "").matchAll(/"icone_png"\s*:\s*"sha256:([0-9a-f]{64})"/g)) {
        if (!icônesLues.has(empreinte)) {
          try {
            const {records: ressources} = await grist(api + cheminIcônes + filtreIcône(empreinte));
            if (ressources.length === 1) icônesLues.set(empreinte, ressources[0].fields.PNG);
          } catch {
            // Le serveur local signalera cette projection comme incomplète.
          }
        }
        if (icônesLues.has(empreinte)) icones[empreinte] = icônesLues.get(empreinte);
      }
      lignes.push({...champs, icones});
    }
    const opérations = json('POST', {id, api, lignes, nom: nomPartage || partage.nom_espace, confirme});
    opérations.headers['X-CSRFToken'] = csrf;
    const résultat = await demander(adresse, opérations);
    const nbAutres = new Set(records.map(({fields}) => fields.Identifiant)
      .filter(cle => /^[\da-f-]{36}$/i.test(cle) && !propres.has(cle))).size;
    return {...résultat, nbAutres, nbNouveaux: lignes.length - résultat.erreurs,
      erreurs: résultat.erreurs + autres.length - lignes.length};
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
          if (affiché) {
            const envoyée = résultat.partage_confirme && !partage.erreur;
            const envoi = partage.erreur || (envoyée
              ? 'Référentiel de la classe partagé.' : 'Envoi du référentiel en attente.');
            const lectures = résultat.erreurs
              ? 'Certains référentiels restent à recevoir.'
              : résultat.nbNouveaux
                ? `${résultat.nbNouveaux} référentiel${résultat.nbNouveaux > 1 ? "s reçus ou mis à jour" : " reçu ou mis à jour"}.`
                : résultat.nbAutres
                  ? 'Les référentiels des autres classes sont à jour.'
                  : 'Aucun référentiel d’une autre installation à recevoir.';
            if (réception && résultat.nbNouveaux) réception.hidden = true;
            afficher(envoi + ' ' + lectures);
          }
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
