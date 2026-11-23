for (const zone of document.querySelectorAll('[data-selection-partage]')) {
  const filtres = zone.querySelector('[data-filtres-partage]');
  const recherche = filtres.querySelector('[data-recherche]');
  const domaine = filtres.querySelector('[data-domaine]');
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
  const domaines = new Set(lignes.map(ligne => ligne.element.dataset.domaine));
  for (const nom of [...domaines].sort((a, b) => a.localeCompare(b, 'fr'))) {
    domaine.add(new Option(nom, nom));
  }

  const taille = 25;
  let page = 0;
  function afficher() {
    const terme = normaliser(recherche.value.trim());
    const visibles = lignes.filter(({ element, case: choix, texte }) =>
      (!domaine.value || element.dataset.domaine === domaine.value) &&
      (!niveau.value || element.dataset.niveau === niveau.value) &&
      (!cochees.checked || choix.checked) && texte.includes(terme));
    const nombrePages = Math.max(1, Math.ceil(visibles.length / taille));
    page = Math.min(page, nombrePages - 1);

    const pageVisible = new Set(visibles.slice(page * taille, (page + 1) * taille));
    for (const ligne of lignes) ligne.element.hidden = !pageVisible.has(ligne);
    const total = lignes.filter(ligne => ligne.case.checked).length;
    const horsFiltre = total - visibles.filter(ligne => ligne.case.checked).length;
    etat.textContent = `${visibles.length} résultat(s) · ${total} sélectionnée(s), dont ${horsFiltre} hors filtre.`;
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
  filtres.hidden = false;
  etat.hidden = false;
  recherche.addEventListener('input', filtrer);
  filtres.addEventListener('change', filtrer);
  zone.addEventListener('change', event => {
    if (event.target.closest('[data-ligne]')) afficher();
  });
  precedente.addEventListener('click', () => { page -= 1; afficher(); });
  suivante.addEventListener('click', () => { page += 1; afficher(); });
  afficher();
}
