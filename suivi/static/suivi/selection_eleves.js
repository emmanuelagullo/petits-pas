for (const groupe of document.querySelectorAll('fieldset')) {
  const commande = groupe.querySelector('[data-selection-eleves], [data-selection-tous]');
  if (!commande || commande.closest('fieldset') !== groupe) continue;
  const cases = Array.from(groupe.querySelectorAll('input[name="eleves"]'));
  const admissibles = cases.filter(champ => !champ.disabled && champ.getAttribute('aria-disabled') !== 'true');
  const compteur = groupe.querySelector('[data-effectif-selection]');
  const estCase = commande.matches('input');
  const actualiser = () => {
    const nombre = admissibles.filter(champ => champ.checked).length;
    const tous = admissibles.length > 0 && nombre === admissibles.length;
    if (estCase) {
      commande.checked = tous;
      commande.indeterminate = nombre > 0 && !tous;
    } else {
      commande.textContent = tous ? 'Tout désélectionner' : 'Tout sélectionner';
    }
    if (compteur) compteur.textContent = `${nombre} élève${nombre > 1 ? 's sélectionnés' : ' sélectionné'}`;
  };
  commande.disabled = !admissibles.length;
  if (!estCase) commande.hidden = !admissibles.length;
  commande.addEventListener(estCase ? 'change' : 'click', () => {
    const cocher = estCase ? commande.checked : admissibles.some(champ => !champ.checked);
    admissibles.forEach(champ => { champ.checked = cocher; });
    actualiser();
    if (!estCase) groupe.dispatchEvent(new Event('change', {bubbles: true}));
  });
  for (const champ of cases) {
    if (champ.hasAttribute('data-version-personnelle')) {
      champ.checked = false;
      champ.addEventListener('click', event => {
        event.preventDefault();
        groupe.querySelector('[data-selection-message]').textContent = champ.dataset.message;
      });
    } else {
      champ.addEventListener('change', actualiser);
    }
  }
  groupe.form?.addEventListener('reset', () => setTimeout(actualiser));
  actualiser();
}

for (const groupe of document.querySelectorAll('[data-choix-eleves]')) {
  const formulaire = groupe.form;
  const choix = formulaire.elements.portee;
  const actualiser = () => {
    groupe.hidden = choix.value !== 'eleves';
    groupe.disabled = groupe.hidden;
  };
  for (const option of choix) option.addEventListener('change', actualiser);
  actualiser();
}
