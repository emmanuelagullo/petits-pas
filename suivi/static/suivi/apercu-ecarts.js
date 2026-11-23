for (const apercu of document.querySelectorAll('[data-apercu-ecarts]')) {
  const filtre = apercu.querySelector('[data-filtre-ecarts]');
  if (!filtre) continue;

  const select = filtre.querySelector('select');
  const compteur = apercu.querySelector('[data-compteur-ecarts]');
  const compteurLibelles = apercu.querySelector('[data-compteur-libelles]');
  const lignes = Array.from(apercu.querySelectorAll('[data-ecart]'));
  filtre.hidden = false;
  compteur.hidden = false;

  function compterLibelles() {
    if (!compteurLibelles) return;
    const cases = Array.from(apercu.querySelectorAll('[name="reprendre_libelle"]:checked'));
    const horsFiltre = cases.filter(caseCochee => caseCochee.closest('[data-ecart]').hidden).length;
    compteurLibelles.hidden = false;
    compteurLibelles.textContent = `${cases.length} choix de libellé sélectionnés, dont ${horsFiltre} hors filtre.`;
  }

  apercu.addEventListener('change', event => {
    if (event.target.name === 'reprendre_libelle') compterLibelles();
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
    compterLibelles();
  }

  select.addEventListener('change', actualiser);
  actualiser();
}
