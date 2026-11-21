(() => {
  const suivis = new Map();
  let sortieConfirmee = false;
  const message = 'Abandonner les modifications non enregistrées ?';
  const etat = formulaire => JSON.stringify(Array.from(new FormData(formulaire), ([nom, valeur]) =>
    [nom, typeof valeur === 'string' ? valeur : [valeur.name, valeur.size, valeur.lastModified]])
    .filter(([, valeur]) => typeof valeur === 'string' || valeur[0]));

  function modifications(exclure) {
    return Array.from(suivis).some(([formulaire, suivi]) =>
      formulaire !== exclure && formulaire.isConnected && suivi.modifie());
  }

  function actualiserProtection() {
    if (modifications()) window.addEventListener('beforeunload', proteger);
    else window.removeEventListener('beforeunload', proteger);
  }

  function proteger(event) {
    if (sortieConfirmee || !modifications()) return;
    event.preventDefault();
    event.returnValue = '';
  }

  function accepterSortie() {
    sortieConfirmee = true;
    setTimeout(() => { sortieConfirmee = false; }, 1000);
  }

  function preparer(formulaire) {
    if (suivis.has(formulaire)) return;
    const initial = etat(formulaire);
    const brouillon = formulaire.hasAttribute('data-brouillon');
    const modifie = () => brouillon || etat(formulaire) !== initial;
    const soumissionInitiale = formulaire.hasAttribute("data-enregistrer-sans-modification");
    const commandes = Array.from(formulaire.querySelectorAll('[data-enregistrer]:not(:disabled)'));
    const retour = formulaire.querySelector('[data-retour-formulaire]');
    const annuler = formulaire.querySelector('[data-annuler-formulaire]');
    const aide = formulaire.querySelector('[data-selection-requise]');
    const selectionComplete = () => !formulaire.hasAttribute('data-eleves-requis') ||
      (formulaire.dataset.elevesRequis === 'portee' && formulaire.elements.portee.value !== 'eleves') ||
      !!formulaire.querySelector('input[name="eleves"]:checked:not(:disabled):not([aria-disabled="true"])');

    function actualiser() {
      const change = modifie();
      const selection = selectionComplete();
      const valide = Array.from(formulaire.elements).every(champ => !champ.willValidate || champ.validity.valid);
      const imageEnCours = formulaire.hasAttribute('data-image-en-cours');
      commandes.forEach(bouton => {
        bouton.disabled = (!change && !soumissionInitiale) || !selection || !valide || imageEnCours;
      });
      if (retour) retour.textContent = change ? 'Annuler' : retour.dataset.retourFormulaire;
      if (annuler) annuler.hidden = !change;
      if (aide) aide.hidden = !change || selection;
      actualiserProtection();
    }

    suivis.set(formulaire, {modifie, actualiser});
    for (const evenement of ['input', 'change', 'validation:actualiser']) {
      formulaire.addEventListener(evenement, () => queueMicrotask(actualiser));
    }
    formulaire.addEventListener('reset', event => {
      if (modifie() && !window.confirm(message)) {
        event.preventDefault();
        return;
      }
      if (brouillon) {
        event.preventDefault();
        accepterSortie();
        location.assign(location.href);
        return;
      }
      setTimeout(() => {
        formulaire.querySelectorAll('select, input[type="radio"], input[type="file"]').forEach(champ => {
          champ.dispatchEvent(new Event('change', {bubbles: true}));
        });
        actualiser();
      });
    });
    actualiser();
  }

  function preparerPage() {
    for (const formulaire of suivis.keys()) {
      if (!formulaire.isConnected) suivis.delete(formulaire);
    }
    document.querySelectorAll('form[data-formulaire-modifie]').forEach(preparer);
    actualiserProtection();
  }

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    const lien = event.target.closest('a[href]');
    if (!lien || lien.hasAttribute('target') || lien.hasAttribute('download') ||
        lien.getAttribute('href').startsWith('#') || !modifications()) return;
    if (!window.confirm(message)) event.preventDefault();
    else accepterSortie();
  });
  document.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    const formulaire = event.target;
    if (formulaire.hasAttribute('data-image-en-cours') || event.submitter?.matches('[data-enregistrer]:disabled')) {
      event.preventDefault();
      return;
    }
    if (modifications(formulaire) && !window.confirm(message)) event.preventDefault();
    else if (!formulaire.hasAttribute('hx-post')) accepterSortie();
  });
  for (const bouton of document.querySelectorAll('[data-champ-action-requis]')) {
    const champ = bouton.form.elements[bouton.dataset.champActionRequis];
    const actualiser = () => {
      const valeur = champ.type === 'password' ? champ.value : champ.value.trim();
      bouton.disabled = !valeur || !champ.validity.valid;
    };
    champ.addEventListener('input', actualiser);
    champ.addEventListener('change', actualiser);
    window.addEventListener('pageshow', actualiser);
    actualiser();
  }
  document.addEventListener('htmx:load', preparerPage);
  window.addEventListener('pageshow', () => {
    sortieConfirmee = false;
    for (const suivi of suivis.values()) suivi.actualiser();
  });
  document.addEventListener('DOMContentLoaded', preparerPage, {once: true});
})();
