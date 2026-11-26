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
    actualiserActionsGrist(form);
  });
});
function adresseCatalogueGrist(lien) {
  try {
    const adresse = new URL(lien);
    const chemin = adresse.pathname.match(/^((?:\/o\/[A-Za-z0-9_-]+)?\/[A-Za-z0-9_-]{8,64})(?:\/[^/]*)?\/?$/);
    return adresse.origin === 'https://grist.numerique.gouv.fr' && !adresse.username &&
      !adresse.password && chemin ? adresse.origin + chemin[1] : '';
  } catch {
    return '';
  }
}

function actualiserActionsGrist(form) {
  const lien = form.elements.url_grist.value.trim();
  const destination = form.elements.destination_grist?.value;
  const disponible = lien ? Boolean(adresseCatalogueGrist(lien)) : Boolean(destination);
  const consultation = form.querySelector('[data-catalogue-consulte]');
  const mêmeCatalogue = !consultation || adresseCatalogueGrist(lien || destination) ===
    adresseCatalogueGrist(consultation.dataset.catalogueConsulte);
  if (consultation) {
    if (form.elements.mode_contenu_grist) {
      form.elements.mode_contenu_grist.disabled = !mêmeCatalogue;
      form.querySelector('[value="enregistrer-mode-grist"]').disabled = !mêmeCatalogue;
    }
    consultation.hidden = mêmeCatalogue;
    if (form.elements.reference_grist) form.elements.reference_grist.disabled = !mêmeCatalogue;
  }
  const publier = form.querySelector('[value="publier-grist"]');
  const consulter = form.querySelector('[value="voir-grist"]');
  const aide = form.querySelector('[data-aide-destination-grist]');
  publier.disabled = consulter.disabled = !disponible;
  publier.classList.toggle('discret', !disponible);
  publier.textContent = mêmeCatalogue && publier.dataset.modeGrist === 'icones'
    ? 'Publier les icônes dans Grist' : 'Publier dans Grist';
  form.parentElement.querySelector('[data-export-zip] button').classList.toggle('discret', disponible);
  aide.hidden = disponible;
  aide.textContent = lien && !disponible
    ? 'Collez le lien d’un document de grist.numerique.gouv.fr.'
    : 'Choisissez un catalogue ou collez son lien pour publier dans Grist.';
}

document.querySelectorAll('[data-publication-grist]').forEach(actualiserActionsGrist);
window.addEventListener('pageshow', () =>
  document.querySelectorAll('[data-publication-grist]').forEach(actualiserActionsGrist));

document.addEventListener('input', event => {
  if (!['url_grist', 'destination_grist', 'reference_grist'].includes(event.target.name)) return;
  const form = event.target.closest('[data-publication-grist]');
  if (!form) return;
  actualiserActionsGrist(form);
  const lien = form.elements.url_grist?.value.trim();
  const catalogue = form.elements.destination_grist?.selectedOptions[0];
  const destination = catalogue?.value ? catalogue.textContent : '';
  const initiale = form.querySelector('[data-destination-grist-initiale]');
  if (initiale) initiale.hidden = true;
  const référence = form.elements.reference_grist;
  const choix = référence?.disabled ? '' : référence?.selectedOptions[0]?.textContent;
  const resume = form.querySelector('[data-choix-grist]');
  resume.textContent = [lien || destination || 'Choisir un catalogue de destination', choix].filter(Boolean).join(' · ');
  resume.hidden = !resume.textContent;
});

document.addEventListener('change', event => {
  const contenu = event.target;
  if (!contenu.matches('#contenu-zip')) return;
  contenu.closest('details').querySelector('summary .aide').textContent = contenu.value
    ? contenu.selectedOptions[0].textContent : 'Compétences seules';
});
