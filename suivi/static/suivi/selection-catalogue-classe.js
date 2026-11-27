(() => {
  const partage = document.querySelector('[data-partage-catalogue]');
  if (!partage) return;

  const resultats = document.getElementById('catalogue-resultats');
  const raccourci = document.querySelector('[data-raccourci-partage]');
  const recherche = document.getElementById('recherche-catalogue');
  const exportClasse = partage.querySelector('[data-partager-classe]');
  const commencer = partage.querySelector('[data-commencer-partage]');
  const formulaire = partage.querySelector('[data-preparer-partage]');
  const envoyer = formulaire.querySelector('button[type="submit"], button[name="action"]');
  const liste = formulaire.querySelector('[data-coches-partage]');
  const listeDepliable = formulaire.querySelector('[data-liste-partage]');
  const etat = formulaire.querySelector('[data-etat-partage]');
  const valeurs = formulaire.querySelector('[data-choix-partage]');
  const cleMemoire = 'petits-pas.selection-partage.' + partage.dataset.classe;
  const bloc = partage.querySelector('[data-export-sur-place]');
  const statut = partage.querySelector('[data-etat-export]');
  let requete;
  let actif = false;
  let coches = new Map();
  try {
    const memoire = JSON.parse(sessionStorage.getItem(cleMemoire));
    if (memoire) {
      actif = memoire.actif;
      coches = new Map(memoire.coches);
    }
  } catch { /* La sélection reste utilisable sur la page courante. */ }

  function actualiser() {
    try {
      sessionStorage.setItem(cleMemoire, JSON.stringify({actif, coches: [...coches]}));
    } catch { /* Le stockage de session est facultatif. */ }

    const source = resultats.querySelector('[data-source-partage]').dataset.sourcePartage;
    const cases = [...resultats.querySelectorAll('[data-case-partage]')];
    const actifs = new Set();
    for (const etiquette of cases) {
      const casePartage = etiquette.querySelector('input');
      etiquette.hidden = !actif;
      casePartage.checked = coches.has(casePartage.value);
      if (casePartage.checked) actifs.add(casePartage.value);
    }
    const total = coches.size;
    const horsFiltre = total - actifs.size;
    partage.querySelector('[data-resume-partage]').textContent = total
      ? `${total} compétence${total > 1 ? 's' : ''} cochée${total > 1 ? 's' : ''}` : '';
    exportClasse.hidden = Boolean(source) || (actif && total > 0);
    commencer.classList.toggle('discret', !exportClasse.hidden || actif);
    for (const bouton of resultats.querySelectorAll('[data-cocher-resultats]')) {
      const casesZone = casesDans(bouton);
      const tous = casesZone.every(c => coches.has(c.value));
      bouton.hidden = !actif || !casesZone.length;
      bouton.closest('[data-portee-partage]')?.classList.toggle('avec-selection', !bouton.hidden);
      const n = casesZone.length;
      bouton.textContent = `${tous ? 'Décocher' : 'Cocher'} ${n} résultat${n > 1 ? 's' : ''}`;
    }
    commencer.setAttribute('aria-pressed', String(actif));
    commencer.textContent = actif ? 'Masquer la sélection' : 'Sélectionner des compétences à exporter';
    formulaire.hidden = !actif;
    raccourci.hidden = !actif;
    raccourci.querySelector('a').textContent = total ? `Aller au partage (${total})` : 'Aller au partage';
    etat.textContent = total ? `${total} compétence${total > 1 ? 's' : ''} cochée${total > 1 ? 's' : ''}${horsFiltre ? ` · ${horsFiltre} hors filtre` : ''}` : 'Cochez les compétences à partager dans la liste.';
    envoyer.disabled = !total;
    envoyer.textContent = total ? `Préparer l’export des ${total} compétence${total > 1 ? 's' : ''}` : 'Préparer l’export de la sélection';
    listeDepliable.hidden = !total;
    valeurs.replaceChildren();
    liste.replaceChildren();
    for (const [cle, libelle] of coches) {
      const champ = document.createElement('input');
      champ.type = 'hidden';
      champ.name = 'competence_partagee';
      champ.value = cle;
      valeurs.append(champ);
      const ligne = document.createElement('li');
      const etiquette = document.createElement('label');
      const casePartage = document.createElement('input');
      casePartage.type = 'checkbox';
      casePartage.checked = true;
      casePartage.value = cle;
      casePartage.dataset.libelle = libelle;
      etiquette.append(casePartage, ' ' + libelle);
      ligne.append(etiquette);
      liste.append(ligne);
    }
  }
  function retourCourant(destination) {
    const retour = new URL(recherche.action);
    retour.search = new URLSearchParams(new FormData(recherche));
    retour.hash = 'partager-competences';
    const chemin = new URL(destination, document.baseURI);
    chemin.searchParams.set('retour', retour.pathname + retour.search + retour.hash);
    return chemin;
  }
  function casesDans(bouton) {
    const zone = bouton.closest('[data-portee-partage]') || resultats;
    return [...zone.querySelectorAll('[data-case-partage] input')];
  }
  function ajouter(choix) {
    const titre = choix.closest('[data-source-partage]')?.querySelector('h2')?.textContent;
    coches.set(choix.value, titre ? `${choix.dataset.libelle} · ${titre}` : choix.dataset.libelle);
  }
  function cocher(event) {
    const choix = event.target;
    if (!choix.matches('input[data-libelle]')) return;
    if (choix.checked) {
      ajouter(choix);
    } else coches.delete(choix.value);
    const depuisRecapitulatif = liste.contains(choix);
    actualiser();
    if (depuisRecapitulatif) (liste.querySelector('input') || commencer).focus();
  }

  commencer.addEventListener('click', () => {
    actif = !actif;
    actualiser();
    if (actif) (resultats.querySelector('[data-case-partage] input') || recherche.elements.q).focus();
  });
  resultats.addEventListener('change', cocher);
  liste.addEventListener('change', cocher);
  resultats.addEventListener('petits-pas:rubriques-actualisees', actualiser);
  async function preparer(url, donnees, declencheur) {
    requete?.abort();
    const instance = new AbortController();
    requete = instance;
    bloc.inert = true;
    bloc.setAttribute('aria-busy', 'true');
    statut.textContent = 'Préparation en cours…';
    try {
      const reponse = await fetch(url, {
        method: donnees ? 'POST' : 'GET', body: donnees, signal: instance.signal,
        credentials: 'same-origin',
      });
      const page = new DOMParser().parseFromString(await reponse.text(), 'text/html');
      const contenu = page.querySelector('[data-preparation-export]');
      if (!contenu || reponse.status >= 500) throw new Error();
      for (const form of contenu.querySelectorAll('form')) {
        form.setAttribute('action', new URL(form.getAttribute('action') || '', reponse.url));
      }
      const titre = document.createElement('h3');
      titre.tabIndex = -1;
      titre.textContent = page.querySelector('h1').textContent;
      const revenir = document.createElement('button');
      revenir.type = 'button';
      revenir.className = 'bouton discret';
      revenir.dataset.fermerPreparation = '';
      revenir.textContent = actif ? 'Revenir à la sélection' : 'Fermer la préparation';
      bloc.replaceChildren(titre, ...contenu.childNodes, revenir);
      bloc.inert = false;
      actualiserExports();
      bloc.dispatchEvent(new Event('petits-pas:rubriques-actualisees', {bubbles: true}));
      titre.focus();
      statut.textContent = '';
    } catch (erreur) {
      if (erreur.name === 'AbortError') return;
      statut.textContent = 'La préparation sur place a échoué. ';
      const secours = document.createElement('a');
      secours.href = url;
      secours.textContent = 'Ouvrir la page d’export';
      if (donnees && declencheur?.form) secours.addEventListener('click', evenement => {
        evenement.preventDefault();
        declencheur.form.setAttribute('action', url);
        const action = document.createElement('input');
        action.type = 'hidden';
        action.name = declencheur.name;
        action.value = declencheur.value;
        declencheur.form.append(action);
        HTMLFormElement.prototype.submit.call(declencheur.form);
      });
      statut.append(secours);
    } finally {
      if (requete === instance) {
        bloc.inert = false;
        bloc.removeAttribute('aria-busy');
      }
    }
  }
  resultats.addEventListener('click', evenement => {
    const bouton = evenement.target.closest('[data-cocher-resultats]');
    if (!bouton) return;
    const cases = casesDans(bouton);
    const retirer = cases.every(c => coches.has(c.value));
    for (const choix of cases) {
      if (retirer) coches.delete(choix.value);
      else ajouter(choix);
    }
    actualiser();
  });
  partage.querySelector('[data-vider-partage]').addEventListener('click', () => {
    coches.clear();
    actualiser();
    commencer.focus();
  });
  raccourci.addEventListener('click', () => { partage.open = true; });
  bloc.addEventListener('click', evenement => {
    if (!evenement.target.closest('[data-fermer-preparation]')) return;
    bloc.replaceChildren();
    (actif ? envoyer : exportClasse).focus();
  });
  exportClasse.addEventListener('click', evenement => {
    exportClasse.href = retourCourant(exportClasse.href);
    if (evenement.ctrlKey || evenement.metaKey || evenement.shiftKey || evenement.altKey) return;
    evenement.preventDefault();
    preparer(exportClasse.href);
  });
  function envoyerSurPlace(evenement) {
    const bouton = evenement.submitter;
    if (!bouton || bouton.value.startsWith('telecharger') || evenement.defaultPrevented) return;
    evenement.preventDefault();
    const form = evenement.target;
    preparer(retourCourant(form.getAttribute('action')), new FormData(form, bouton), bouton);
  }
  formulaire.addEventListener('submit', envoyerSurPlace);
  bloc.addEventListener('submit', envoyerSurPlace);
  window.addEventListener('pageshow', actualiser);
  partage.querySelector('[data-commandes-partage]').hidden = false;
  actualiser();
})();
