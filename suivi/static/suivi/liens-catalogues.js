(() => {
  const afficherBoutons = zone => {
    if (navigator.clipboard) {
      zone.querySelectorAll('[data-copier-lien]').forEach(bouton => { bouton.hidden = false; });
    }
  };
  afficherBoutons(document);
  document.addEventListener('htmx:load', evenement => afficherBoutons(evenement.target));
  document.addEventListener('click', async evenement => {
    const bouton = evenement.target.closest('[data-copier-lien]');
    if (!bouton) return;
    const zone = bouton.closest('[data-lien-catalogue]');
    const champ = zone.querySelector('input');
    const statut = zone.querySelector('[role="status"]');
    try {
      await navigator.clipboard.writeText(champ.value);
      statut.textContent = 'Lien copié.';
    } catch {
      champ.focus();
      champ.select();
      statut.textContent = 'Lien sélectionné. Vous pouvez le copier.';
    }
  });
})();
