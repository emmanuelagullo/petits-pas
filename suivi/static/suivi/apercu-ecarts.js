for (const apercu of document.querySelectorAll('[data-apercu-ecarts]')) {
  const filtre = apercu.querySelector('[data-filtre-ecarts]');
  if (!filtre) continue;

  const select = filtre.querySelector('select');
  const compteur = apercu.querySelector('[data-compteur-ecarts]');
  const compteurReprises = apercu.querySelector('[data-compteur-reprises]');
  const lignes = Array.from(apercu.querySelectorAll('[data-ecart]'));
  filtre.hidden = false;
  compteur.hidden = false;

  function compterReprises() {
    if (!compteurReprises) return;
    const cases = Array.from(apercu.querySelectorAll('[name="reprendre_libelle"]:checked, [name="reprendre_phrase"]:checked'));
    const horsFiltre = cases.filter(caseCochee => caseCochee.closest('[data-ecart]').hidden).length;
    compteurReprises.hidden = false;
    compteurReprises.textContent = `${cases.length} choix de reprise sélectionnés, dont ${horsFiltre} hors filtre.`;
  }

  apercu.addEventListener('change', event => {
    if (['reprendre_libelle', 'reprendre_phrase'].includes(event.target.name)) compterReprises();
  });

  function actualiser() {
    const types = select.value.split(' ');
    let visibles = 0;
    for (const ligne of lignes) {
      const champs = ligne.dataset.ecart.split(' ');
      ligne.hidden = Boolean(select.value) && !types.some(type => champs.includes(type));
      if (!ligne.hidden) visibles += 1;
    }
    compteur.textContent = `${visibles} sur ${lignes.length} compétences modifiées affichées. Le filtre change uniquement l’affichage.`;
    compterReprises();
  }

  select.addEventListener('change', actualiser);
  actualiser();
}
