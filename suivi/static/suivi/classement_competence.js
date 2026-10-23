/* Filtrage local : ne remplace ni le formulaire ni les fichiers sélectionnés. */
(function () {
  function initialiserClassement(racine) {
    racine.querySelectorAll('[data-classement-competence]').forEach(function (groupe) {
      if (groupe.dataset.classementInitialise) return;
      const domaine = groupe.querySelector('[name="domaine"]');
      const sousDomaine = groupe.querySelector('[name="sous_domaine"]');
      const zone = groupe.querySelector('[data-selecteur-sous-domaine]');
      const message = groupe.querySelector('[data-message-classement]');
      if (!domaine || !sousDomaine || !zone || !message) return;
      const options = Array.from(sousDomaine.options, option => option.cloneNode(true));
      groupe.dataset.classementInitialise = 'oui';
      function actualiser(changement) {
        const avant = sousDomaine.value;
        const proposees = options.filter(option => !option.value || option.dataset.domaine === domaine.value);
        const conserve = proposees.some(option => option.value === avant);
        sousDomaine.replaceChildren(...proposees.map(option => option.cloneNode(true)));
        sousDomaine.value = conserve ? avant : '';
        const vide = proposees.every(option => !option.value);
        const erreur = sousDomaine.getAttribute('aria-invalid') === 'true';
        zone.hidden = vide && !erreur;
        sousDomaine.disabled = vide && !erreur;
        message.textContent = vide ? 'Ce domaine ne comporte pas de sous-domaines.'
          : changement ? 'Le domaine a changé : choisissez un sous-domaine si nécessaire.'
          : !conserve && avant ? 'Choisissez un sous-domaine de ce domaine.' : '';
      }
      domaine.addEventListener('change', () => actualiser(true));
      actualiser(false);
    });
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {initialiserClassement};
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initialiserClassement(document), {once: true});
    else initialiserClassement(document);
    document.addEventListener('htmx:load', event => initialiserClassement(event.target));
  }
})();
