/* Le formulaire GET reste disponible lorsque la recherche dynamique échoue. */
(() => {
  const form = document.getElementById('recherche-catalogue');
  if (!form) return;

  const resultats = document.getElementById('catalogue-resultats');
  const etat = document.getElementById('catalogue-etat');
  const {source, domaine, sous_domaine: groupe, portee} = form.elements;
  const ouvrirAjout = form.querySelector('[data-ouvrir-ajout]');
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
      const creationOuverte = resultats.querySelector('details[open]');
      domaine.replaceChildren(options.cloneNode(true));
      groupe.replaceChildren(groupes.cloneNode(true));
      url.searchParams.set('domaine', domaine.value);
      url.searchParams.set('sous_domaine', groupe.value);
      resultats.replaceChildren(contenu.content);
      if (creationOuverte) resultats.querySelector('details')?.setAttribute('open', '');
      resultats.inert = false;
      history.replaceState(history.state, '', url);
      etat.textContent = `${nombre} résultat${nombre > 1 ? 's' : ''}`;
    } catch (erreur) {
      if (version === sequence && erreur.name !== 'AbortError')
        etat.textContent = 'Recherche indisponible. Utilisez le bouton Rechercher.';
    } finally {
      if (version === sequence) resultats.removeAttribute('aria-busy');
    }
  }

  function rechercher(evenement) {
    const version = invalider();
    if (evenement.target === source) {
      domaine.value = '';
      portee.value = '';
      portee.disabled = !!source.value;
      portee.closest('[data-filtre-portee]').hidden = !!source.value;
    }
    if (evenement.target === source || evenement.target === domaine) groupe.value = '';
    if (ouvrirAjout) {
      const ajout = new URL(form.action);
      ajout.search = new URLSearchParams(new FormData(form));
      ajout.searchParams.set('ajouter', '1');
      ouvrirAjout.href = ajout;
    }
    resultats.inert = true;
    resultats.setAttribute('aria-busy', 'true');
    etat.textContent = 'Recherche en cours…';
    minuterie = setTimeout(() => actualiser(version), evenement.type === 'input' ? 250 : 0);
  }

  form.elements.q.addEventListener('input', rechercher);
  form.addEventListener('change', evenement => {
    if (evenement.target instanceof HTMLSelectElement) rechercher(evenement);
  });
  form.addEventListener('submit', invalider);
})();
