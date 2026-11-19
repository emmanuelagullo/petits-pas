(() => {
  let origine, survol;
  const effacerSurvol = () => {
    survol?.removeAttribute('data-depot');
    survol = null;
  };
  document.querySelectorAll('[data-poignee]').forEach(poignee => {
    poignee.hidden = false;
    poignee.addEventListener('dragstart', evenement => {
      origine = poignee.closest('[data-rubrique]');
      evenement.dataTransfer.setData('text/plain', origine.id);
      evenement.dataTransfer.effectAllowed = 'move';
    });
    poignee.addEventListener('dragend', () => {
      origine = null;
      effacerSurvol();
    });
  });
  document.addEventListener('dragover', evenement => {
    const cible = evenement.target.closest('[data-rubrique]');
    if (!origine || !cible || cible === origine || cible.parentElement !== origine.parentElement) {
      effacerSurvol();
      return;
    }
    evenement.preventDefault();
    evenement.dataTransfer.dropEffect = 'move';
    if (cible !== survol) effacerSurvol();
    survol = cible;
    const boite = cible.firstElementChild.getBoundingClientRect();
    cible.dataset.depot = evenement.clientY < boite.top + boite.height / 2 ? 'avant' : 'apres';
  });
  document.addEventListener('drop', evenement => {
    const cible = evenement.target.closest('[data-rubrique]');
    if (!origine || !survol || cible !== survol) return;
    evenement.preventDefault();
    const formulaire = origine.querySelector('[data-form-ordre]');
    formulaire.elements.cible_id.value = cible.dataset.rubrique;
    formulaire.elements.apres.value = cible.dataset.depot === 'apres' ? '1' : '';
    effacerSurvol();
    formulaire.requestSubmit(formulaire.querySelector('[value="glisser"]'));
  });
})();
