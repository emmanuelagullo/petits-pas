for (const zone of document.querySelectorAll('[data-selection-partage]')) {
  const filtres = zone.querySelector('[data-filtres-partage]');
  const recherche = zone.querySelector('[data-recherche]');
  const domaine = filtres.querySelector('[data-domaine]');
  const sousDomaine = filtres.querySelector('[data-sous-domaine]');
  const rubriques = [...zone.querySelectorAll('.rubriques-competences details')];
  const niveau = filtres.querySelector('[data-niveau]');
  const cochees = filtres.querySelector('[data-cochees]');
  const etat = zone.querySelector('[data-etat]');
  const pages = zone.querySelector('[data-pages]');
  const precedente = pages.querySelector('[data-precedente]');
  const suivante = pages.querySelector('[data-suivante]');
  const position = pages.querySelector('[data-position]');
  const telecharger = zone.querySelector('[data-telecharger]');
  const normaliser = texte => texte.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('fr');
  const lignes = Array.from(zone.querySelectorAll('[data-ligne]'), element => ({
    element,
    case: element.querySelector('input'),
    texte: normaliser(element.textContent),
  }));
  function chargerOptions(select, champ, lignesProposees) {
    const choix = select.value;
    const valeurs = new Set(lignesProposees.map(ligne => ligne.element.dataset[champ]).filter(Boolean));
    select.length = 1;
    for (const nom of [...valeurs].sort((a, b) => a.localeCompare(b, 'fr'))) {
      select.add(new Option(nom, nom));
    }
    select.value = valeurs.has(choix) ? choix : '';
  }
  function chargerSousDomaines() {
    chargerOptions(sousDomaine, 'sousDomaine', lignes.filter(
      ligne => !domaine.value || ligne.element.dataset.domaine === domaine.value));
  }
  chargerOptions(domaine, 'domaine', lignes);
  chargerSousDomaines();

  const taille = 25;
  let page = 0;
  function afficher() {
    const terme = normaliser(recherche.value.trim());
    const visibles = lignes.filter(({ element, case: choix, texte }) =>
      (!domaine.value || element.dataset.domaine === domaine.value) &&
      (!sousDomaine.value || element.dataset.sousDomaine === sousDomaine.value) &&
      (!niveau.value || element.dataset.niveau === niveau.value) &&
      (!cochees.checked || choix.checked) && texte.includes(terme));
    const nombrePages = Math.max(1, Math.ceil(visibles.length / taille));
    page = Math.min(page, nombrePages - 1);

    const pageVisible = new Set(visibles.slice(page * taille, (page + 1) * taille));
    for (const ligne of lignes) ligne.element.hidden = !pageVisible.has(ligne);
    const filtrage = terme || domaine.value || sousDomaine.value || niveau.value || cochees.checked;
    for (const rubrique of rubriques) {
      rubrique.hidden = !rubrique.querySelector('[data-ligne]:not([hidden])');
      if (filtrage && !rubrique.hidden) rubrique.open = true;
    }
    const total = lignes.filter(ligne => ligne.case.checked).length;
    const horsFiltre = total - visibles.filter(ligne => ligne.case.checked).length;
    const actifs = [domaine.value, sousDomaine.value, niveau.value, cochees.checked ? 'Compétences cochées' : ''].filter(Boolean);
    etat.textContent = `${visibles.length} résultat(s) · ${total} sélectionnée(s), dont ${horsFiltre} hors filtre.`
      + (actifs.length ? ` Filtres actifs : ${actifs.join(' · ')}.` : '');
    pages.hidden = nombrePages === 1;
    precedente.disabled = page === 0;
    suivante.disabled = page === nombrePages - 1;
    position.textContent = `Page ${page + 1} sur ${nombrePages}`;
    if (telecharger) {
      telecharger.disabled = total === 0;
      telecharger.textContent = `Télécharger la sélection (${total})`;
    }
  }

  function filtrer() {
    page = 0;
    afficher();
  }
  zone.querySelector('[data-barre-partage]').hidden = false;
  recherche.addEventListener('input', filtrer);
  filtres.addEventListener('change', event => {
    if (event.target === domaine) chargerSousDomaines();
    filtrer();
  });
  zone.addEventListener('change', event => {
    if (event.target.closest('[data-ligne]')) afficher();
  });
  precedente.addEventListener('click', () => { page -= 1; afficher(); });
  suivante.addEventListener('click', () => { page += 1; afficher(); });
  afficher();
}


const choixEdition = document.querySelector('[data-choix-edition-partage]');
if (choixEdition) {
  const edition = choixEdition.elements.edition;
  const initiale = edition.value;
  choixEdition.querySelector('[data-afficher-edition]').hidden = true;
  edition.addEventListener('change', () => {
    const coches = document.querySelector('[data-selection-partage] input[name="competence"]:checked, [data-selection-partage] input[name="reprise"]:checked');
    if (coches && !window.confirm('Changer d’édition recharge la page. Voulez-vous quitter la sélection en cours ?')) {
      edition.value = initiale;
      return;
    }
    choixEdition.requestSubmit();
  });
}
