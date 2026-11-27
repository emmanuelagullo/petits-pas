document.addEventListener('htmx:beforeRequest', evenement => {
  const id = evenement.detail.elt.dataset.ouvrirRubrique;
  if (!id) return;
  const rubrique = document.getElementById(id);
  if (!rubrique) return;
  rubrique.hidden = false;
  rubrique.open = true;
});
document.addEventListener('htmx:afterSwap', evenement => {
  if (evenement.detail.target.id !== 'contenu-import-classe') return;
  const champ = evenement.detail.target.querySelector('input[type="file"]');
  champ?.focus({preventScroll: true});
});
