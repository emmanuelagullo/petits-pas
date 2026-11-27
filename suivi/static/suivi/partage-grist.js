(() => {
  for (const invitation of document.querySelectorAll('[data-invitation-grist]')) {
    if (!navigator.clipboard || window.parent === window) continue;
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
  const résuméEspace = document.querySelector('[data-resume-espace]');
  const repèreEspace = résuméEspace || document.querySelector('[data-nom-espace]');
  const nomEspace = résuméEspace ? résuméEspace.closest('summary').querySelector('h2') : repèreEspace;
  const relancer = document.querySelector('[data-relancer-synchro]');
  const étiquette = document.querySelector('[data-etiquette-synchro]');
  const détails = document.querySelector('[data-details-synchro]');
  const journal = document.querySelector('[data-journal-synchro]');
  const projection = document.querySelector('[data-projection-partagee]');
  const raccordement = document.querySelector('[data-raccordement-grist][data-document-actif]');
  if (raccordement) {
    const documentGrist = lien => {
      try {
        const url = new URL(lien.trim());
        if (url.origin !== 'https://grist.numerique.gouv.fr' || url.username || url.password) return;
        return url.pathname.match(/^(?:\/o\/[A-Za-z0-9_-]+)?\/([A-Za-z0-9_-]{8,64})(?:\/[^/]+)?(?:\/p\/[A-Za-z0-9_-]+)?\/?$/)?.[1];
      } catch {
        return undefined;
      }
    };
    const champ = raccordement.elements.namedItem('grist');
    const bouton = raccordement.querySelector('[value="raccorder"]');
    const initial = documentGrist(raccordement.dataset.documentActif);
    const confirmer = raccordement.elements.namedItem('changement').value;
    const actualiser = () => {
      const destination = documentGrist(champ.value);
      const changement = Boolean(destination && destination !== initial);
      const lienModifié = destination === initial && champ.value.trim() !== raccordement.dataset.documentActif;
      bouton.disabled = !changement && !lienModifié;
      bouton.classList.toggle('avertissement-orange', changement);
      bouton.textContent = changement
        ? destination === confirmer ? 'Confirmer le changement d’espace' : 'Vérifier le changement d’espace'
        : lienModifié ? 'Enregistrer le lien du document' : 'Confirmer le raccordement';
    };
    champ.addEventListener('input', actualiser);
    champ.addEventListener('change', actualiser);
    window.addEventListener('pageshow', actualiser);
    actualiser();
  }
  function afficher(message, état, enregistrer = true) {
    if (etat) etat.textContent = message;
    if (étiquette) {
      étiquette.textContent = état;
      étiquette.closest('summary').classList.toggle('pastille-positive', état === 'À jour');
      étiquette.closest('summary').classList.toggle('alerte', état === 'À reprendre');
    }
    if (!journal || !enregistrer) return;
    détails.hidden = false;
    const ligne = document.createElement('li');
    const heure = document.createElement('time');
    const date = new Date();
    heure.dateTime = date.toISOString();
    heure.textContent = date.toLocaleString('fr-FR');
    const résultat = document.createElement('strong');
    résultat.textContent = état;
    ligne.append(heure, ' · ', résultat, ' · ', message);
    journal.prepend(ligne);
    if (journal.children.length > 10) journal.lastElementChild.remove();
    détails.querySelector('summary .aide').textContent =
      date.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'}) + ' · ' + état;
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
          const réponse = await fetch(formulaire.action, {
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

  function activerPublicationÉquipe() {
    const publication = document.querySelector('[data-publier-equipe-grist][hidden]');
    if (!publication) return;
    publication.hidden = false;
    const bouton = publication.querySelector('button');
    const état = publication.querySelector('[role=status]');
    publication.addEventListener('submit', async event => {
      event.preventDefault();
      if (bouton.disabled) return;
      bouton.disabled = true;
      état.textContent = 'Publication en cours…';
      try {
        const réponse = await fetch(publication.action, {
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
  activerPublicationÉquipe();
  document.addEventListener('htmx:afterSwap', activerPublicationÉquipe);
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
    let erreurRéception = false;
    const {records} = await grist(index).catch(() => {
      erreurRéception = true;
      return {records: []};
    });
    const reçus = partage.recues;
    const autres = [...new Set(records.map(({fields}) => fields)
      .filter(f => /^[\da-f-]{36}$/i.test(f.Identifiant) && !propres.has(f.Identifiant)
        && reçus[f.Identifiant] !== f.Empreinte).map(f => f.Identifiant))];
    const lignes = [];
    const icônesLues = new Map();
    for (const identifiant of autres) {
      // L’index ne contient que des métadonnées. Le contenu local n’est jamais demandé.
      const filtre = encodeURIComponent(JSON.stringify({Identifiant: [identifiant]}));
      const réponse = await grist(`${documents}?filter=${filtre}`).catch(() => null);
      if (réponse?.records.length !== 1) continue;
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
    let editions;
    try {
      const {tables} = await grist(api + '/tables');
      editions = [];
      const mode = metadata.records.find(r => r.fields.Identifiant === 'mode-contenu')?.fields.Nom;
      if (mode !== 'icones' && tables.some(table => table.id === 'Editions')) {
        const index = await grist(api + '/tables/Editions/records');
        editions = index.records.map(({fields: {Referentiel, Titre, Numero, Contenu}}) => {
          let origine;
          try { origine = JSON.parse(Contenu)?.origine_classe_grist; } catch { /* Ancienne édition. */ }
          return {Referentiel, Titre, Numero,
            Contenu: Contenu ? JSON.stringify({origine_classe_grist: origine}) : ''};
        });
      }
    } catch {
      // Une indisponibilité du catalogue ne bloque pas l’envoi ni la réception des classes.
    }
    const opérations = json('POST', {id, api, lignes, editions, nom: nomPartage || partage.nom_espace, confirme});
    opérations.headers['X-CSRFToken'] = csrf;
    const résultat = await demander(adresse, opérations);
    const nbAutres = new Set(records.map(({fields}) => fields.Identifiant)
      .filter(cle => /^[\da-f-]{36}$/i.test(cle) && !propres.has(cle))).size;
    return {...résultat, nbAutres, nbNouveaux: lignes.length - résultat.erreurs,
      erreurs: résultat.erreurs + autres.length - lignes.length + Number(erreurRéception), erreurRéception};
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

  const listeReçue = document.querySelector('[data-referentiels-espace]');
  const compteur = document.querySelector('[data-compte-referentiels]');
  let réceptionÀAfficher = false;

  async function afficherRéception() {
    if (!listeReçue || !réceptionÀAfficher || listeReçue.contains(document.activeElement)) return;
    const réponse = await fetch(listeReçue.dataset.referentielsEspace, {cache: 'no-store'});
    if (!réponse.ok) throw new Error('Liste de référentiels indisponible');
    const page = new DOMParser().parseFromString(await réponse.text(), 'text/html');
    const liste = page.querySelector('[data-referentiels-espace]');
    const total = page.querySelector('[data-compte-referentiels]');
    const résumé = page.querySelector('[data-resume-espace]');
    if (!liste || !total || résumé?.dataset.partage !== repèreEspace.dataset.partage) return;
    if (listeReçue.contains(document.activeElement)) return;
    listeReçue.replaceChildren(...liste.childNodes);
    listeReçue.dispatchEvent(new CustomEvent('petits-pas:panneaux', {bubbles: true}));
    window.htmx?.process(listeReçue);
    listeReçue.closest("details").open = true;
    compteur.textContent = total.textContent;
    réceptionÀAfficher = false;
  }

  async function vérifier() {
    if (enCours) return;
    if (!navigator.onLine) {
      afficher('La synchronisation reprendra à la reconnexion.', 'Hors ligne', false);
      return;
    }
    enCours = true;
    if (relancer) {
      relancer.disabled = true;
      relancer.querySelector('[data-libelle-synchro]').textContent = 'Synchronisation en cours…';
    }
    afficher('Envoi et réception des référentiels.', 'En cours', false);
    try {
      const {partages, propres} = await demander(adresse);
      for (const partage of partages) {
        const affiché = repèreEspace?.dataset.partage === partage.id;
        try {
          const résultat = await synchroniser(partage, new Set(propres));
          if (affiché && projection && résultat.partage_confirme && !partage.erreur)
            projection.textContent = 'Référentiel de la classe partagé';
          let problèmeÉquipe = false;
          try {
            await synchroniserÉquipe(partage);
          } catch {
            problèmeÉquipe = true;
          }
          if (affiché && résultat.nom) nomEspace.textContent = résultat.nom;
          if (affiché) {
            const envoyée = résultat.partage_confirme && !partage.erreur;
            const envoi = partage.erreur || (envoyée
              ? partage.contenu === null ? 'Référentiel de la classe déjà partagé.' : 'Référentiel de la classe envoyé.'
              : 'Envoi du référentiel en attente.');
            const lectures = résultat.erreurRéception
              ? 'Impossible de vérifier les référentiels à recevoir.' : résultat.erreurs
              ? 'Certains référentiels restent à recevoir.'
              : résultat.nbNouveaux
                ? `${résultat.nbNouveaux} référentiel${résultat.nbNouveaux > 1 ? "s reçus ou mis à jour" : " reçu ou mis à jour"}.`
                : résultat.nbAutres
                  ? 'Les référentiels des autres classes sont à jour.'
                  : 'Aucun référentiel d’une autre installation à recevoir.';
            réceptionÀAfficher ||= résultat.nbNouveaux > 0 || résultat.catalogue_modifie;
            let actualiserListe = '';
            try {
              await afficherRéception();
            } catch {
              actualiserListe = ' Rechargez la page pour afficher les référentiels reçus.';
            }
            const équipe = problèmeÉquipe ? ' Le référentiel d’équipe reste à synchroniser.' : '';
            afficher(envoi + ' ' + lectures + équipe + actualiserListe,
              résultat.erreurs || partage.erreur || problèmeÉquipe ? 'À reprendre' : 'À jour');
          }
        } catch {
          if (affiché) afficher('Réessayez quand le document est accessible.', 'À reprendre');
        }
      }
    } catch {
      afficher('Impossible de joindre Petits Pas. Réessayez à la reconnexion.', 'À reprendre');
    } finally {
      enCours = false;
      if (relancer) {
        relancer.disabled = false;
        relancer.querySelector('[data-libelle-synchro]').textContent = 'Synchroniser maintenant';
      }
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
