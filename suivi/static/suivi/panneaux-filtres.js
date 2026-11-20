for (const barre of document.querySelectorAll('[data-barre-filtres]')) {
  const commandes = document.createElement('div');
  commandes.className = 'commandes-filtres';
  barre.prepend(commandes);
  for (const [index, panneau] of Array.from(barre.querySelectorAll(':scope > details[data-panneau-filtre]')).entries()) {
    const titre = panneau.querySelector('summary');
    panneau.id ||= (barre.id || 'panneau-filtre') + '-' + index;
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
    panneau.addEventListener('toggle', actualiser);
    new MutationObserver(actualiser).observe(panneau, {attributeFilter: ['hidden']});
    commandes.append(bouton);
    titre.hidden = true;
    actualiser();
  }
  barre.classList.add('barre-filtres-active');
}

const sommaire = document.querySelector('[data-sommaire-page]');
if (sommaire) {
  const titres = Array.from(document.querySelectorAll('[data-titre-sommaire][id]'));
  if (titres.length >= 4) {
    const liste = sommaire.querySelector('ol');
    for (const titre of titres) {
      const item = document.createElement('li');
      const lien = document.createElement('a');
      lien.href = '#' + titre.id;
      lien.textContent = titre.textContent;
      lien.addEventListener('click', () => {
        titre.focus({preventScroll: true});
        if (matchMedia('(max-width: 65rem)').matches) sommaire.open = false;
      });
      item.append(lien);
      liste.append(item);
    }
    sommaire.querySelector('a[href="#haut-page-suivi"]').addEventListener('click', () => {
      document.getElementById('haut-page-suivi').focus({preventScroll: true});
      if (matchMedia('(max-width: 65rem)').matches) sommaire.open = false;
    });
    sommaire.addEventListener('keydown', event => {
      if (event.key === 'Escape' && sommaire.open) {
        sommaire.open = false;
        sommaire.querySelector('summary').focus();
      }
    });
    sommaire.open = matchMedia('(min-width: 65.01rem)').matches;
    sommaire.hidden = false;
    sommaire.parentElement.classList.add('avec-sommaire');
  }
}

const apercuCarnet = document.querySelector('[data-apercu-carnet]');
if (apercuCarnet) {
  apercuCarnet.addEventListener('change', event => {
    const panneau = event.target.closest('[data-panneau-filtre]');
    const action = panneau?.querySelector('button[name="panneau"]');
    if (action) apercuCarnet.requestSubmit(action);
  });
}
