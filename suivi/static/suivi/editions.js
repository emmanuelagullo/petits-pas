// Calcul en jours civils UTC, comme dans la saisie des périodes de Pas à Pas.
const millisecondesParJour = 86400000;

for (const zone of document.querySelectorAll('[data-dates-edition]')) {
  const form = zone.closest('form');
  const {observations, periode, calcul_periode: calcul, debut, fin, duree} = form.elements;
  const raccourcis = JSON.parse(zone.querySelector('script').textContent);
  const explication = form.querySelector('[data-explication-automatique]');
  const champDuree = zone.querySelector('[data-duree-edition]');
  function actualiser() {
    const active = ['periode', 'reussites'].includes(observations.value);
    zone.hidden = !active && !zone.querySelector('.errorlist');
    explication.hidden = observations.value !== '';
    const symbolique = raccourcis[periode.value];
    const parDuree = !symbolique && calcul.value === 'duree';
    if (symbolique) {
      [debut.value, fin.value] = symbolique;
    } else if (parDuree) {
      const jours = duree.valueAsNumber;
      const origine = debut.valueAsNumber;
      fin.valueAsNumber = Number.isInteger(jours) && jours >= 1 && jours <= 366 &&
        Number.isFinite(origine) ? origine + (jours - 1) * millisecondesParJour : NaN;
    }
    if (!parDuree && debut.value && fin.value) {
      const jours = (fin.valueAsNumber - debut.valueAsNumber) / millisecondesParJour + 1;
      duree.value = jours > 0 ? jours : '';
    }
    debut.disabled = !active || Boolean(symbolique);
    fin.disabled = !active || Boolean(symbolique) || parDuree;
    calcul.disabled = !active || Boolean(symbolique);
    periode.disabled = !active;
    champDuree.hidden = !parDuree;
    duree.disabled = !active || !parDuree;
  }
  zone.addEventListener('input', actualiser);
  zone.addEventListener('change', actualiser);
  observations.addEventListener('change', () => {
    if (!debut.value && !fin.value && !duree.value && !zone.querySelector('.errorlist')) {
      periode.value = 'rentree';
    }
    actualiser();
  });
  actualiser();
}

const edition = document.querySelector('#preparer-carnets');
if (edition) {
  const format = edition.elements.format;
  const enfants = Array.from(edition.querySelectorAll('[name="eleves"]'));
  const action = edition.querySelector('[data-preparer-edition]');
  const apercu = edition.querySelector('[data-apercu-edition]');
  const sections = Array.from(edition.querySelectorAll('[name="sections_eleves"]'));
  const dates = edition.querySelector('[data-dates-edition]');
  const etat = edition.querySelector('[data-etat-edition]');
  const optionsCartes = edition.querySelector('[data-options-cartes]');
  const optionsCarnet = edition.querySelector('[data-options-carnet]');
  function memoriserMiseEnPage() {
    edition.elements.mise_en_page_ouverte.value =
      !optionsCartes.hidden && optionsCartes.open ? 'cartes' :
      !optionsCarnet.hidden && optionsCarnet.open ? 'carnet' : '';
  }
  edition.addEventListener('submit', memoriserMiseEnPage);
  function actualiser() {
    const sectionsRetenues = sections.filter(section => section.checked).map(section => section.value);
    const nombre = enfants.filter(eleve => eleve.checked &&
      (!sectionsRetenues.length || sectionsRetenues.includes(eleve.dataset.section))).length;
    const cartes = format.value === 'cartes';
    const grille = format.value === 'grille';
    const pwa = !apercu;
    optionsCartes.hidden = !cartes;
    optionsCarnet.hidden = cartes || grille;
    edition.elements.ordre_cartes.disabled = !edition.elements.planches_compactes.checked;
    for (const groupe of edition.querySelectorAll('[data-filtres-carnet]')) {
      groupe.hidden = groupe.disabled = cartes || grille;
    }
    const parcoursComplet = !cartes && !grille && edition.elements.parcours.value === 'complet';
    edition.querySelector('[data-resume-eleves]').textContent =
      `${nombre ? `${nombre} élève${nombre > 1 ? 's sélectionnés' : ' sélectionné'}` : 'Aucun élève sélectionné'} · ${parcoursComplet ? 'Parcours complet' : edition.dataset.annee}`;
    const avecPeriode = ['periode', 'reussites'].includes(edition.elements.observations.value);
    const debut = dates.querySelector('[name="debut"]').value;
    const fin = dates.querySelector('[name="fin"]').value;
    const periodeValide = !avecPeriode || (debut && fin && debut <= fin);
    etat.textContent = !nombre ? 'Sélectionnez au moins un élève dans les sections retenues.' :
      !periodeValide ? 'Indiquez une période valide pour préparer cette édition.' : '';
    action.disabled = !nombre || !periodeValide;
    if (apercu) {
      apercu.disabled = action.disabled;
      apercu.hidden = grille || format.value === 'sequence';
    }
    action.textContent = {
      zip: 'Télécharger l’archive ZIP',
      pdf: pwa ? 'Préparer l’impression des carnets' : 'Télécharger les carnets en un PDF',
      sequence: 'Préparer les carnets un par un',
      grille: 'Afficher la grille',
      cartes: pwa ? 'Préparer les cartes' : 'Télécharger les cartes en PDF',
    }[format.value];
  }
  edition.addEventListener('change', actualiser);
  dates.addEventListener('input', actualiser);
  actualiser();
}

const grille = document.querySelector('[data-defilement-grille]');
if (grille) {
  const cle = 'grille-position:' + location.pathname + location.search;
  try {
    const position = sessionStorage.getItem(cle);
    if (position && performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
      const [left, top] = JSON.parse(position);
      grille.scrollTo(left, top);
    }
    addEventListener('pagehide', () => {
      try { sessionStorage.setItem(cle, JSON.stringify([grille.scrollLeft, grille.scrollTop])); }
      catch (_) { /* Le retour ancré reste disponible. */ }
    });
  } catch (_) { /* La mémoire de position est facultative. */ }
}

for (const arbre of document.querySelectorAll('[data-recherche-competences]')) {
  const outils = arbre.querySelector('[data-outils-competences]');
  const recherche = outils.querySelector('input[type="search"]');
  const cochees = outils.querySelector('[data-competences-cochees]');
  const compteur = outils.querySelector('[data-compteur-competences]');
  const cases = [...arbre.querySelectorAll('input[name="competences"]')];
  const normaliser = texte => texte.toLocaleLowerCase('fr').normalize('NFD').replace(/\p{Diacritic}/gu, '');
  const libelles = new Map(cases.map(champ => {
    const texte = [champ.parentElement.textContent];
    let panneau = champ.closest('details');
    while (panneau && arbre.contains(panneau)) {
      texte.push(panneau.querySelector(':scope > summary').textContent);
      panneau = panneau.parentElement.closest('details');
    }
    return [champ, normaliser(texte.join(' '))];
  }));
  const branches = [...arbre.querySelectorAll('[data-branche-rubrique]')].map(element => ({
    element,
    commande: element.querySelector(':scope > label input'),
    panneau: element.querySelector(':scope > details'),
    total: element.querySelector(':scope > details > summary [data-rubrique-total]'),
    cases: [...element.querySelectorAll('input[name="competences"]')],
  }));
  let ouvertures = null;
  function actualiser() {
    recherche.disabled = cochees.checked;
    const terme = cochees.checked ? "" : normaliser(recherche.value.trim());
    const filtre = Boolean(terme || cochees.checked);
    if (filtre && !ouvertures) ouvertures = branches.map(branche => branche.panneau.open);
    for (const champ of cases) {
      champ.parentElement.hidden = (cochees.checked && !champ.checked) || !libelles.get(champ).includes(terme);
    }
    branches.forEach(({element, commande, panneau, total, cases: descendants}, index) => {
      const nombre = descendants.filter(champ => champ.checked).length;
      const visible = descendants.some(champ => !champ.parentElement.hidden);
      commande.checked = nombre === descendants.length;
      commande.indeterminate = nombre > 0 && !commande.checked;
      total.textContent = `${nombre} / ${descendants.length}`;
      element.hidden = !visible;
      if (filtre) panneau.open = visible;
      else if (ouvertures) panneau.open = ouvertures[index];
    });
    if (!filtre) ouvertures = null;
    const nombre = cases.filter(champ => champ.checked).length;
    const selection = nombre
      ? `${nombre} compétence${nombre === 1 ? ' sélectionnée' : 's sélectionnées'}`
      : 'Toutes les compétences suivies sont prises en compte avant le filtre d’observations';
    const resultats = cases.filter(champ => !champ.parentElement.hidden).length;
    compteur.textContent = terme ? `${selection} · ${resultats} résultat${resultats === 1 ? '' : 's'}` : selection;
  }
  for (const {commande, cases: descendants} of branches) {
    commande.parentElement.hidden = false;
    commande.addEventListener('change', () => {
      for (const champ of descendants) champ.checked = commande.checked;
    });
  }
  outils.hidden = false;
  recherche.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) event.preventDefault();
  });
  recherche.addEventListener('input', actualiser);
  arbre.addEventListener('change', actualiser);
  actualiser();
}

const sequence = document.querySelector('[data-sequence-carnets]');
if (sequence) {
  sequence.addEventListener('submit', event => {
    const actif = event.submitter;
    if (!actif?.matches('button[name="carnet"]')) return;
    const suivant = actif.closest('li').nextElementSibling?.querySelector('button');
    if (suivant) {
      for (const bouton of sequence.querySelectorAll('button')) {
        bouton.classList.toggle('discret', bouton !== suivant);
      }
      suivant.focus();
    }
  });
}
