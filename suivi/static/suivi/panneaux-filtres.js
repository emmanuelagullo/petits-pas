for (const barre of document.querySelectorAll('[data-barre-filtres]')) {
  const commandes = document.createElement('div');
  commandes.className = 'commandes-filtres';
  barre.prepend(commandes);
  for (const [index, panneau] of Array.from(barre.querySelectorAll(':scope > details[data-panneau-filtre]')).entries()) {
    const titre = panneau.querySelector('summary');
    panneau.id ||= (barre.id || 'panneau-filtre') + '-' + index;
    const cleMemoire = panneau.dataset.memoireFiltre;
    if (cleMemoire) {
      try {
        const ouvert = sessionStorage.getItem(cleMemoire);
        if (ouvert !== null) panneau.open = ouvert === '1';
      } catch { /* Le panneau fonctionne aussi sans stockage de session. */ }
    }
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'bouton discret bouton-panneau';
    bouton.textContent = titre.textContent.trim();
    bouton.setAttribute('aria-controls', panneau.id);
    function actualiser() {
      bouton.hidden = panneau.hidden;
      bouton.setAttribute('aria-expanded', String(panneau.open));
    }
    bouton.addEventListener('click', () => { panneau.open = !panneau.open; actualiser(); });
    panneau.addEventListener('toggle', () => {
      actualiser();
      if (cleMemoire) {
        try { sessionStorage.setItem(cleMemoire, panneau.open ? '1' : '0'); }
        catch { /* Le panneau fonctionne aussi sans stockage de session. */ }
      }
    });
    new MutationObserver(actualiser).observe(panneau, {attributeFilter: ['hidden']});
    commandes.append(bouton);
    titre.hidden = true;
    actualiser();
  }
  barre.classList.add('barre-filtres-active');
}

const apercuCarnet = document.querySelector('[data-apercu-carnet]');
if (apercuCarnet) {
  apercuCarnet.addEventListener('change', event => {
    const panneau = event.target.closest('[data-panneau-filtre]');
    const action = panneau?.querySelector('button[name="panneau"]');
    if (action) apercuCarnet.requestSubmit(action);
  });
}
