(() => {
  const formulaire = '[data-commutateur-licences]';
  let canal;
  try { canal = new BroadcastChannel('petits-pas:affichage-licences'); } catch { /* Facultatif. */ }

  function appliquer(visible) {
    document.body.dataset.licencesVisibles = visible ? '1' : '0';
    for (const form of document.querySelectorAll(formulaire)) form.elements.visible.checked = visible;
  }
  canal?.addEventListener('message', evenement => appliquer(evenement.data === true));
  document.addEventListener('change', async evenement => {
    const caseLicence = evenement.target;
    const form = caseLicence.closest(formulaire);
    if (!form || caseLicence.name !== 'visible') return;
    const precedent = document.body.dataset.licencesVisibles === '1';
    const donnees = new FormData(form);
    donnees.set('retour', location.pathname + location.search);
    caseLicence.disabled = true;
    try {
      const reponse = await fetch(form.action, {method: 'POST', body: donnees, headers: {Accept: 'application/json'}});
      if (!reponse.ok) throw new Error();
      const {visible} = await reponse.json();
      appliquer(visible);
      canal?.postMessage(visible);
    } catch {
      appliquer(precedent);
      form.classList.add('affichage-licences-reessayer');
    } finally {
      caseLicence.disabled = false;
    }
  });
  document.addEventListener('htmx:afterSwap', evenement => {
    const rubrique = evenement.target;
    if (rubrique.id !== 'licence-nouvelles-competences') return;
    rubrique.open = true;
    rubrique.querySelector('#enregistrer-politique-licence')?.focus({preventScroll: true});
  });
  const cible = document.getElementById(location.hash.slice(1));
  if (cible?.matches('#menu-licences, #licence-nouvelles-competences')) {
    const menu = cible.closest('.menu-competence-catalogue');
    if (menu) menu.open = true;
    if (cible instanceof HTMLDetailsElement) cible.open = true;
  }
  document.documentElement.classList.add('affichage-licences-dynamique');
})();
