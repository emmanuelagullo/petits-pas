/* Recherche locale : mêmes seuils que consultation_referentiels.py. */
(() => {
  const normaliser = texte => texte.toLowerCase().replace(/ß/g, 'ss').normalize('NFKD').replace(/\p{M}/gu, '');
  const mots = texte => texte.match(/[\p{L}\p{N}_]+/gu) || [];
  const distance = (a, b) => {
    let ligne = Array.from({length: b.length + 1}, (_, i) => i), precedente;
    for (let i = 1; i <= a.length; i++) {
      const suivante = [i];
      for (let j = 1; j <= b.length; j++) {
        suivante[j] = Math.min(suivante[j - 1] + 1, ligne[j] + 1, ligne[j - 1] + (a[i - 1] !== b[j - 1]));
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
          suivante[j] = Math.min(suivante[j], precedente[j - 2] + 1);
      }
      precedente = ligne; ligne = suivante;
    }
    return ligne[b.length];
  };
  const score = (texte, termes) => {
    let total = 0;
    const candidats = mots(texte);
    for (const terme of termes) {
      if (texte.includes(terme)) continue;
      const seuil = terme.length >= 9 ? 2 : terme.length >= 5 ? 1 : 0;
      if (!seuil) return Infinity;
      let meilleur = seuil + 1;
      for (const mot of candidats)
        if (Math.abs(mot.length - terme.length) <= seuil) meilleur = Math.min(meilleur, distance(terme, mot));
      if (meilleur > seuil) return Infinity;
      total += meilleur;
    }
    return total;
  };
  // Permet de vérifier les règles sans navigateur ni dépendance supplémentaire.
  if (typeof module !== 'undefined') module.exports = {normaliser, mots, score};
  if (typeof document === 'undefined') return;
  const donnees = document.getElementById('catalogue-referentiel');
  if (!donnees) return;
  const catalogue = JSON.parse(donnees.textContent).map(ligne => ({...ligne, texte: normaliser(ligne.libelle)}));
  const form = document.querySelector('[data-recherche-referentiel]');
  const liste = document.querySelector('[data-resultats-referentiel]');
  const compteur = document.querySelector('[data-compteur-referentiel]');
  const nav = document.querySelector('[data-pagination-locale]');
  const precedent = nav.querySelector('[data-precedent]'), suivant = nav.querySelector('[data-suivant]');
  const position = nav.querySelector('[data-position]');
  let page = Math.max(1, Number(new URL(location.href).searchParams.get('page')) || 1), resultats = [];
  const afficher = () => {
    const pages = Math.max(1, Math.ceil(resultats.length / 60));
    page = Math.min(page, pages);
    const fragment = document.createDocumentFragment();
    for (const ligne of resultats.slice((page - 1) * 60, page * 60)) {
      const li = document.createElement('li'), div = document.createElement('div');
      const titre = document.createElement('strong'), meta = document.createElement('p');
      li.className = 'entree'; titre.textContent = ligne.libelle;
      meta.textContent = [ligne.domaine, ligne.groupe, ligne.niveau, ligne.code,
        ligne.active === false ? 'masquée pour les prochaines saisies' : ''].filter(Boolean).join(' · ');
      div.append(titre, meta); li.append(div); fragment.append(li);
    }
    if (!resultats.length) {
      const vide = document.createElement('li'); vide.textContent = 'Aucun apprentissage ne correspond à ces filtres.'; fragment.append(vide);
    }
    liste.replaceChildren(fragment);
    compteur.textContent = `${resultats.length} résultat${resultats.length > 1 ? 's' : ''}.`;
    nav.hidden = pages <= 1;
    precedent.disabled = page <= 1; suivant.disabled = page >= pages;
    position.textContent = `Page ${page} sur ${pages}`;
  };
  const filtrer = (reset = true) => {
    if (reset) page = 1;
    const termes = mots(normaliser(form.elements.q.value));
    resultats = catalogue.filter(ligne => (!form.elements.domaine.value || ligne.domaine === form.elements.domaine.value)
      && (!form.elements.niveau.value || ligne.niveau === form.elements.niveau.value))
      .map(ligne => ({ligne, score: score(ligne.texte, termes)}))
      .filter(item => Number.isFinite(item.score)).sort((a, b) => a.score - b.score).map(item => item.ligne);
    afficher();
  };
  form.elements.q.addEventListener('input', () => filtrer());
  ['domaine', 'niveau'].forEach(nom => form.elements[nom].addEventListener('change', () => filtrer()));
  form.addEventListener('submit', event => {
    // Changer la présentation source/classe demande un nouveau catalogue au serveur.
    if (form.elements.lecture && form.elements.lecture.value !== form.dataset.lecture) return;
    event.preventDefault(); filtrer();
  });
  precedent.addEventListener('click', () => { page--; afficher(); });
  suivant.addEventListener('click', () => { page++; afficher(); });
  filtrer(false);
  document.querySelectorAll('[data-pagination-serveur]').forEach(element => { element.hidden = true; });
})();
