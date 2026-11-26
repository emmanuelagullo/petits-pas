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
  const actualisation = document.querySelector('[data-actualisation-catalogues]');
  if (actualisation) {
    let enCours = false;
    async function actualiser() {
      if (enCours || document.hidden || !navigator.onLine) return;
      enCours = true;
      const statut = actualisation.querySelector('[role=status]');
      try {
        const réponse = await fetch(actualisation.getAttribute("action"), {method: 'POST', body: new FormData(actualisation)});
        if (!réponse.ok) throw new Error();
        const {editions, erreurs} = await réponse.json();
        if (!editions && !erreurs.length) return;
        statut.textContent = erreurs.length ? erreurs.join(' · ') : 'De nouvelles éditions ont été reçues.';
        actualisation.hidden = false;
      } catch {
        statut.textContent = 'L’actualisation des catalogues est en attente.';
        actualisation.hidden = false;
      } finally {
        enCours = false;
      }
    }
    window.addEventListener('online', actualiser);
    setInterval(actualiser, 300000);
    actualiser();
  }
})();
