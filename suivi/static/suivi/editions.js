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
  function actualiser() {
    const nombre = enfants.filter(eleve => eleve.checked).length;
    const cartes = format.value === 'cartes';
    const grille = format.value === 'grille';
    const pwa = !apercu;
    edition.querySelector('[data-options-cartes]').hidden = !cartes;
    edition.querySelector('[data-options-carnet]').hidden = cartes || grille;
    edition.querySelector('[data-resume-eleves]').textContent =
      `${nombre} enfant${nombre > 1 ? 's' : ''} sélectionné${nombre > 1 ? 's' : ''}`;
    action.disabled = !nombre;
    if (apercu) {
      apercu.disabled = !nombre;
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
