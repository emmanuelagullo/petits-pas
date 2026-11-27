/* Le formulaire GET reste disponible lorsque la recherche dynamique échoue. */
(() => {
  const form = document.getElementById('recherche-catalogue');
  if (!form) return;

  const resultats = document.getElementById('catalogue-resultats');
  const etat = document.getElementById('catalogue-etat');
  const {source, domaine, sous_domaine: groupe} = form.elements;
  const soumettre = form.querySelector('.soumission-catalogue button');
  const actions = form.querySelector('[data-actions-catalogue]');
  const filtres = form.querySelector('[data-filtres-actifs]');
  const effacer = form.querySelector('[data-effacer-recherche]');
  let minuterie, requete, sequence = 0;

  function invalider() {
    clearTimeout(minuterie);
    requete?.abort();
    return ++sequence;
  }

  async function actualiser(version) {
    const url = new URL(form.action);
    url.search = new URLSearchParams(new FormData(form));
    const fragment = new URL(url);
    fragment.searchParams.set('fragment', '1');
    requete = new AbortController();
    try {
      const reponse = await fetch(fragment, {signal: requete.signal, credentials: 'same-origin'});
      if (!reponse.ok || reponse.headers.get('X-Petits-Pas-Catalogue') !== '1')
        throw new Error('Recherche indisponible');
      const html = await reponse.text();
      if (version !== sequence) return;
      const contenu = document.createElement('template');
      contenu.innerHTML = html;
      const options = contenu.content.querySelector('[data-options-domaines]').content;
      const groupes = contenu.content.querySelector('[data-options-groupes]').content;
      const nombre = Number(contenu.content.querySelector('[data-nombre-resultats]').dataset.nombreResultats);
      const creationOuverte = actions.querySelector('details[open]');
      const focusCreation = actions.contains(document.activeElement);
      actions.replaceChildren(contenu.content.querySelector('[data-actions-creation]').content.cloneNode(true));
      filtres.replaceChildren(contenu.content.querySelector('[data-filtres-actifs]').content.cloneNode(true));
      effacer.replaceChildren(contenu.content.querySelector('[data-effacer-recherche]').content.cloneNode(true));
      actions.inert = false;
      domaine.replaceChildren(options.cloneNode(true));
      groupe.replaceChildren(groupes.cloneNode(true));
      url.searchParams.set('domaine', domaine.value);
      url.searchParams.set('sous_domaine', groupe.value);
      resultats.replaceChildren(contenu.content);
      resultats.dispatchEvent(new Event("petits-pas:rubriques-actualisees", {bubbles: true}));
      const nouveauDepliant = actions.querySelector('details');
      if (creationOuverte && nouveauDepliant) nouveauDepliant.open = true;
      if (focusCreation) (nouveauDepliant?.querySelector('summary') || form.elements.q).focus({preventScroll: true});
      resultats.inert = false;
      history.replaceState(history.state, '', url);
      const importer = document.querySelector('[data-importer-zip]');
      if (importer) {
        const destination = new URL(importer.href);
        destination.searchParams.set('retour', url.pathname + url.search);
        importer.href = destination;
        destination.hash = '';
        importer.setAttribute('hx-get', destination.pathname + destination.search);
        window.htmx?.process(importer);
      }
      etat.textContent = `${nombre} résultat${nombre > 1 ? 's' : ''}`;
    } catch (erreur) {
      if (version === sequence && erreur.name !== 'AbortError') {
        soumettre.hidden = false;
        etat.textContent = 'Recherche indisponible. Utilisez le bouton Rechercher.';
      }
    } finally {
      if (version === sequence) resultats.removeAttribute('aria-busy');
    }
  }

  function rechercher(evenement) {
    const version = invalider();
    if (source && evenement.target === source) domaine.value = '';
    if ((source && evenement.target === source) || evenement.target === domaine) groupe.value = '';
    actions.inert = true;
    resultats.inert = true;
    resultats.setAttribute('aria-busy', 'true');
    etat.textContent = 'Recherche en cours…';
    minuterie = setTimeout(() => actualiser(version), evenement.type === 'input' ? 250 : 0);
  }

  form.elements.q.addEventListener('input', rechercher);
  form.addEventListener('change', evenement => {
    if (evenement.target instanceof HTMLSelectElement || ["inclure_masquees", "inclure_competences_masquees"].includes(evenement.target.name)) rechercher(evenement);
  });
  form.addEventListener('submit', evenement => {
    if (soumettre.hidden) {
      evenement.preventDefault();
      rechercher(evenement);
    }
  });
  soumettre.hidden = true;
})();
