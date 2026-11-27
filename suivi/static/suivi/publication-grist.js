function documentGristPourExport(lien) {
  try {
    const adresse = new URL(lien);
    const chemin = adresse.pathname.match(/^(?:\/o\/[A-Za-z0-9_-]+)?\/([A-Za-z0-9_-]{8,64})(?:\/[^/]+)?(?:\/p\/[A-Za-z0-9_-]+)?\/?$/);
    return adresse.origin === 'https://grist.numerique.gouv.fr' && !adresse.username &&
      !adresse.password && chemin ? chemin[1] : '';
  } catch {
    return '';
  }
}

function actualiserExportClasse(form, ouvrirOptions = false) {
  const lien = form.elements.url_grist.value.trim();
  const destination = form.elements.destination_grist?.value || '';
  const identifiant = documentGristPourExport(lien || destination);
  const consultation = form.querySelector('[data-consulter-grist]');
  const adresseConsultee = consultation.dataset.catalogueConsulte;
  const reference = form.elements.reference_grist;
  const mêmeCatalogue = adresseConsultee && identifiant &&
    identifiant === documentGristPourExport(adresseConsultee);
  const grist = form.elements.destination_export.value === 'grist';
  const publier = form.querySelector('[value="publier-grist"]');
  const consulter = form.querySelector('[value="voir-grist"]');
  const aide = form.querySelector('[data-aide-destination-grist]');
  const options = form.querySelector('[data-options-export]');
  const resume = form.querySelector('[data-resume-grist]');
  const données = resume.dataset;
  if (adresseConsultee) {
    if (form.elements.mode_contenu_grist) {
      form.elements.mode_contenu_grist.disabled = !mêmeCatalogue;
      form.querySelector('[value="enregistrer-mode-grist"]').disabled = !mêmeCatalogue;
    }
  }
  if (reference && adresseConsultee) reference.disabled = !mêmeCatalogue;

  const icones = Number(données.icones);
  const compétences = Number(données.competences);
  const nombre = (n, nom, pluriel = nom + 's') => n + ' ' + (n === 1 ? nom : pluriel);
  const mode = mêmeCatalogue ? publier.dataset.modeGrist : '';
  const iconesSeules = mode === 'icones';
  const sélection = form.elements.destination_grist?.selectedOptions[0];
  const nom = (mêmeCatalogue && données.nomDestination) ||
    (!lien && sélection?.value ? sélection.textContent.split(' · ')[0] : lien);
  const numéroVérifié = mêmeCatalogue && (!reference || reference.value === données.referenceVerifiee);
  consultation.hidden = Boolean(numéroVérifié && (données.editionPrevue || iconesSeules));
  const édition = numéroVérifié && données.editionPrevue
    ? (données.editionIdentique === 'oui' ? 'Contenu identique à l’édition ' : 'Édition ') + données.editionPrevue
    : 'Publication du référentiel · Numéro vérifié à la publication';
  const effet = !mode ? ['Contenu et numéro vérifiés à la publication']
    : iconesSeules ? ['Icônes seules', nombre(icones, 'icône ajoutée', 'icônes ajoutées')]
      : [édition, nombre(compétences, 'compétence')];
  if (mode === 'complet' && icones) effet.push(nombre(icones, 'icône ajoutée', 'icônes ajoutées'));
  if (données.licence) effet.push(données.licence);

  form.querySelector('[data-choix-grist]').textContent = nom || 'Choisissez un catalogue de destination';
  form.querySelector('[data-effet-grist]').textContent = effet.join(' · ');
  publier.disabled = consulter.disabled = !identifiant;
  if (!form.hasAttribute('aria-busy')) {
    publier.textContent = iconesSeules ? 'Publier les icônes dans Grist' : 'Publier dans Grist';
  }
  aide.hidden = Boolean(identifiant);
  aide.textContent = lien && !identifiant
    ? 'Collez le lien d’un document de grist.numerique.gouv.fr.'
    : 'Choisissez un catalogue ou collez son lien pour publier dans Grist.';

  const iconesZip = form.elements.inclure_icones?.value === 'oui';
  form.querySelector('[data-resume-icones-zip]').textContent = iconesZip
    ? ' · ' + nombre(icones, 'icône ajoutée', 'icônes ajoutées') : '';
  form.querySelector('[data-resume-options-export]').textContent = grist
    ? (nom || 'Choisir un catalogue')
    : (iconesZip ? 'Compétences et ' + nombre(icones, 'icône ajoutée', 'icônes ajoutées') : 'Compétences');
  if (ouvrirOptions && grist && !identifiant) options.open = true;
}

document.addEventListener('submit', event => {
  const form = event.target;
  if (!form.matches('[data-export-classe]')) return;
  if (form.hasAttribute('aria-busy')) {
    event.preventDefault();
    return;
  }
  if (event.submitter?.value === 'publier-grist') {
    form.setAttribute('aria-busy', 'true');
    event.submitter.textContent = 'Publication en cours…';
  }
});

function actualiserExports() {
  for (const form of document.querySelectorAll('[data-export-classe]')) {
    form.removeAttribute('aria-busy');
    actualiserExportClasse(form);
  }
}
actualiserExports();
window.addEventListener('pageshow', actualiserExports);
document.addEventListener('input', event => {
  const form = event.target.closest('[data-export-classe]');
  if (form) actualiserExportClasse(form, event.target.name === 'destination_export');
});
