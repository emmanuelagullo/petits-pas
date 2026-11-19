for (const bouton of document.querySelectorAll('[data-selection-eleves]')) {
  const groupe = bouton.closest('fieldset');
  const cases = Array.from(groupe.querySelectorAll('input[name="eleves"]:not(:disabled)'));
  if (!cases.length) continue;
  const compteur = groupe.querySelector('[data-effectif-selection]');
  const actualiser = () => {
    const nombre = cases.filter(champ => champ.checked).length;
    bouton.textContent = nombre === cases.length ? 'Tout désélectionner' : 'Tout sélectionner';
    compteur.textContent = `${nombre} élève${nombre > 1 ? 's sélectionnés' : ' sélectionné'}`;
  };
  bouton.hidden = false;
  bouton.addEventListener('click', () => {
    const cocher = cases.some(champ => !champ.checked);
    cases.forEach(champ => { champ.checked = cocher; });
    actualiser();
  });
  cases.forEach(champ => champ.addEventListener('change', actualiser));
  actualiser();
}
