document.addEventListener('submit', event => {
  if (!event.target.matches('[data-publication-grist]')) return;
  const bouton = event.submitter;
  if (event.target.getAttribute('aria-busy') === 'true') {
    event.preventDefault();
    return;
  }
  if (bouton?.value !== 'publier-grist') return;
  event.target.setAttribute('aria-busy', 'true');
  bouton.textContent = 'Publication en cours…';
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('[data-publication-grist][aria-busy]').forEach(form => {
    form.removeAttribute('aria-busy');
    form.querySelector('[value="publier-grist"]').textContent = 'Publier dans Grist';
  });
});
document.addEventListener('input', event => {
  if (!['url_grist', 'destination_grist', 'reference_grist'].includes(event.target.name)) return;
  const form = event.target.closest('[data-publication-grist]');
  if (!form) return;
  const lien = form.elements.url_grist?.value.trim();
  const catalogue = form.elements.destination_grist?.selectedOptions[0];
  const destination = catalogue?.value ? catalogue.textContent : '';
  const initiale = form.querySelector('[data-destination-grist-initiale]');
  if (initiale) initiale.hidden = true;
  const choix = form.elements.reference_grist?.selectedOptions[0]?.textContent;
  const resume = form.querySelector('[data-choix-grist]');
  resume.textContent = [lien || destination || 'Choisir un catalogue de destination', choix].filter(Boolean).join(' · ');
  resume.hidden = !resume.textContent;
});
