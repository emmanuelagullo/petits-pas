(() => {
  const sommaire = document.querySelector('[data-sommaire-page]');
  if (!sommaire) return;
  const page = sommaire.parentElement;
  const titres = [...page.querySelectorAll('[data-titre-sommaire][id]')];
  if (!page.hasAttribute('data-sommaire-structure') && titres.length < 4) return;
  const large = matchMedia('(min-width: 90rem)');
  const racine = sommaire.querySelector('ol');
  const entrees = new Map();
  const parents = new Set(titres.map(titre => titre.dataset.titreSommaire).filter(Boolean));
  let active;
  function rejoindre(titre) {
    if (!titre) return;
    const volet = titre.closest('summary')?.parentElement;
    if (volet?.matches('details')) volet.open = true;
    titre.focus({preventScroll: true});
    if (!large.matches) sommaire.open = false;
    signaler(titre.id);
  }

  for (const titre of titres) {
    const parent = entrees.get(titre.dataset.titreSommaire);
    const item = document.createElement('li');
    const ligne = document.createElement('div');
    ligne.className = 'ligne-sommaire';
    const lien = document.createElement('a');
    lien.href = '#' + titre.id;
    lien.textContent = titre.textContent.trim();
    lien.addEventListener('click', () => rejoindre(titre));
    item.append(ligne);
    ligne.append(lien);
    (parent?.liste || racine).append(item);
    const entree = {ligne, lien, parent};

    if (parents.has(titre.id)) {
      const liste = document.createElement('ol');
      liste.id = 'sommaire-' + titre.id;
      liste.hidden = Boolean(parent);
      const chevron = document.createElement('button');
      chevron.type = 'button';
      chevron.setAttribute('aria-label', 'Sous-entrées de ' + lien.textContent);
      chevron.setAttribute('aria-controls', liste.id);
      chevron.setAttribute('aria-expanded', String(!liste.hidden));
      chevron.addEventListener('click', () => {
        liste.hidden = !liste.hidden;
        chevron.setAttribute('aria-expanded', String(!liste.hidden));
        rendreActive();
      });
      ligne.append(chevron);
      item.append(liste);
      entree.liste = liste;
    }
    entrees.set(titre.id, entree);
  }

  function rendreActive() {
    for (const entree of entrees.values()) {
      entree.ligne.removeAttribute('data-section-active');
      entree.lien.removeAttribute('aria-current');
    }
    if (!active) return;
    active.lien.setAttribute('aria-current', 'location');
    let repere = active;
    for (let entree = active; entree.parent; entree = entree.parent) {
      if (entree.parent.liste.hidden) repere = entree.parent;
    }
    if (repere !== active) repere.ligne.setAttribute('data-section-active', '');
    if (!sommaire.open) return;
    const lien = repere.lien.getBoundingClientRect();
    const panneau = sommaire.getBoundingClientRect();
    if (lien.top < panneau.top) sommaire.scrollTop += lien.top - panneau.top;
    else if (lien.bottom > panneau.bottom) sommaire.scrollTop += lien.bottom - panneau.bottom;
  }

  function signaler(id) {
    const entree = entrees.get(id);
    if (entree === active) return;
    active = entree;
    rendreActive();
  }

  function depuisElement(element) {
    if (!element || !page.contains(element) || sommaire.contains(element)) return;
    const id = element.closest('[data-zone-sommaire]')?.dataset.zoneSommaire;
    if (id) signaler(id);
  }

  function depuisDefilement() {
    const seuil = Math.min(innerHeight * .2, 140);
    const fond = scrollY > 0 && scrollY + innerHeight >= document.documentElement.scrollHeight - 2;
    const courant = titres.findLast(titre => titre.getBoundingClientRect().top <= seuil);
    signaler((fond ? titres.at(-1) : courant)?.id);
  }

  function depuisAncre() {
    const element = document.getElementById(location.hash.slice(1));
    if (element?.matches('[data-titre-sommaire]')) signaler(element.id);
    else if (element?.closest('[data-zone-sommaire]')) depuisElement(element);
    else depuisDefilement();
  }

  sommaire.querySelector('a[href="#haut-page-suivi"]').addEventListener('click', () => {
    rejoindre(document.getElementById('haut-page-suivi'));
  });
  sommaire.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sommaire.open && !large.matches) {
      sommaire.open = false;
      sommaire.querySelector('summary').focus();
    }
  });
  page.addEventListener('click', event => depuisElement(event.target));
  page.addEventListener('change', event => depuisElement(event.target));
  page.addEventListener('htmx:afterSwap', event => depuisElement(event.target));
  sommaire.addEventListener('toggle', rendreActive);
  large.addEventListener('change', () => { sommaire.open = large.matches; });
  addEventListener('hashchange', depuisAncre);
  addEventListener('pageshow', depuisAncre);
  let image;
  addEventListener('scroll', () => {
    cancelAnimationFrame(image);
    image = requestAnimationFrame(depuisDefilement);
  }, {passive: true});
  sommaire.open = large.matches;
  sommaire.hidden = false;
  page.classList.add('avec-sommaire');
  depuisAncre();
})();
