function initialiserPanneaux(racine) {
  for (const barre of racine.querySelectorAll('[data-barre-filtres]:not(.barre-filtres-active)')) {
    const panneaux = Array.from(barre.querySelectorAll(':scope > details[data-panneau-filtre]'));
    if (!panneaux.length) continue;
    const commandes = document.createElement('div');
    commandes.className = 'commandes-filtres';
    barre.prepend(commandes);
    for (const [index, panneau] of panneaux.entries()) {
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
      const principal = panneau.hasAttribute('data-panneau-principal');
      function actualiserTitre() {
        if (!barre.hasAttribute('data-barre-catalogue')) {
          bouton.className = 'bouton discret bouton-panneau';
          bouton.textContent = titre.textContent.trim();
          return;
        }
        bouton.className = titre.className.replace('bouton-depliant', 'bouton-panneau');
        bouton.replaceChildren(...Array.from(titre.childNodes, enfant => {
          if (!(enfant instanceof Element)) return enfant.cloneNode(true);
          const copie = document.createElement('span');
          copie.className = enfant.className;
          copie.textContent = enfant.textContent;
          return copie;
        }));
      }
      actualiserTitre();
      new MutationObserver(actualiserTitre).observe(titre, {subtree: true, childList: true, characterData: true, attributes: true});
      bouton.setAttribute('aria-controls', panneau.id);
      if (titre.hasAttribute('aria-label')) bouton.setAttribute('aria-label', titre.getAttribute('aria-label'));
      function actualiser() {
        bouton.hidden = panneau.hidden;
        bouton.setAttribute('aria-expanded', String(panneau.open));
      }
      bouton.addEventListener('click', () => {
        const ouvrir = !panneau.open;
        if (ouvrir && barre.classList.contains('carte-catalogue') && !principal) {
          for (const voisin of panneaux) {
            if (!voisin.hasAttribute('data-panneau-principal')) voisin.open = false;
          }
        }
        panneau.open = ouvrir;
        actualiser();
      });
      panneau.addEventListener('toggle', () => {
        actualiser();
        if (cleMemoire) {
          try { sessionStorage.setItem(cleMemoire, panneau.open ? '1' : '0'); }
          catch { /* Le panneau fonctionne aussi sans stockage de session. */ }
        }
      });
      new MutationObserver(actualiser).observe(panneau, {attributeFilter: ['hidden']});
      if (principal) {
        const entete = document.createElement('h2');
        entete.className = 'titre-carte-catalogue';
        entete.append(bouton);
        barre.prepend(entete);
      } else {
        commandes.append(bouton);
      }
      titre.hidden = true;
      actualiser();
    }
    barre.classList.add('barre-filtres-active');
  }
}

initialiserPanneaux(document);
document.addEventListener('htmx:load', evenement => initialiserPanneaux(evenement.detail.elt.parentElement || document));
document.addEventListener('petits-pas:panneaux', evenement => initialiserPanneaux(evenement.target));

const apercuCarnet = document.querySelector('[data-apercu-carnet]');
if (apercuCarnet) {
  apercuCarnet.addEventListener('change', event => {
    const panneau = event.target.closest('[data-panneau-filtre]');
    const action = panneau?.querySelector('button[name="panneau"]');
    if (action) apercuCarnet.requestSubmit(action);
  });
}
