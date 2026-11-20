for (const choix of document.querySelectorAll('select[name="observations"]')) {
  const dates = choix.form.querySelector('[data-dates-edition]');
  if (!dates) continue;
  function actualiser() {
    dates.hidden = !['periode', 'reussites'].includes(choix.value) && !dates.querySelector('.errorlist');
  }
  choix.addEventListener('change', actualiser);
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
      `${nombre} enfant${nombre > 1 ? 's' : ''} · ${parcoursComplet ? 'Parcours complet' : edition.dataset.annee}`;
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

for (const liste of document.querySelectorAll('[data-recherche-competences]')) {
  const champ = liste.querySelector('input[type="search"]');
  champ.closest('label').hidden = false;
  champ.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) event.preventDefault();
  });
  function normaliser(texte) {
    return texte.toLocaleLowerCase('fr').normalize('NFD').replace(/\p{Diacritic}/gu, '');
  }
  champ.addEventListener('input', () => {
    const recherche = normaliser(champ.value.trim());
    for (const caseChoix of liste.querySelectorAll('input[type="checkbox"]')) {
      const ligne = caseChoix.closest('label').parentElement;
      ligne.hidden = !caseChoix.checked && !normaliser(ligne.textContent).includes(recherche);
    }
  });
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

for (const branche of document.querySelectorAll('[data-branche-rubrique]')) {
  const parent = branche.querySelector('[data-bascule-rubrique]');
  const panneau = branche.querySelector('details');
  const resume = branche.querySelector('[data-rubrique-total]');
  const titre = branche.querySelector('[data-rubrique-repli]');
  const enfants = Array.from(branche.querySelectorAll('[name="rubriques"]'));
  parent.closest('label').hidden = false;
  resume.hidden = false;
  titre.hidden = true;
  panneau.querySelector('summary').setAttribute('aria-label', 'Sous-rubriques de ' + titre.textContent);
  function actualiser() {
    const nombre = enfants.filter(enfant => enfant.checked).length;
    parent.checked = nombre === enfants.length;
    parent.indeterminate = nombre > 0 && nombre < enfants.length;
    resume.textContent = nombre + ' sur ' + enfants.length;
  }
  parent.addEventListener('change', () => {
    for (const enfant of enfants) enfant.checked = parent.checked;
    actualiser();
  });
  panneau.addEventListener('change', actualiser);
  actualiser();
  panneau.open = parent.indeterminate || enfants.length <= 2;
}
