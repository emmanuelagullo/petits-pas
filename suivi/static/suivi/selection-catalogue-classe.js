(() => {
  const partage = document.querySelector('[data-partage-catalogue]');
  if (!partage) return;

  const resultats = document.getElementById('catalogue-resultats');
  const raccourci = document.querySelector('[data-raccourci-partage]');
  const recherche = document.getElementById('recherche-catalogue');
  const exportClasse = partage.querySelector('[data-partager-classe]');
  const commencer = partage.querySelector('[data-commencer-partage]');
  const formulaire = partage.querySelector('[data-preparer-partage]');
  const envoyer = formulaire.querySelector('button[type="submit"], button[name="action"]');
  const liste = formulaire.querySelector('[data-coches-partage]');
  const listeDepliable = formulaire.querySelector('[data-liste-partage]');
  const etat = formulaire.querySelector('[data-etat-partage]');
  const valeurs = formulaire.querySelector('[data-choix-partage]');
  const cleMemoire = 'petits-pas.selection-partage.' + partage.dataset.classe;
  let actif = false;
  let coches = new Map();
  try {
    const memoire = JSON.parse(sessionStorage.getItem(cleMemoire));
    if (memoire) {
      actif = memoire.actif;
      coches = new Map(memoire.coches);
    }
  } catch { /* La sélection reste utilisable sur la page courante. */ }

  function actualiser() {
    try {
      sessionStorage.setItem(cleMemoire, JSON.stringify({actif, coches: [...coches]}));
    } catch { /* Le stockage de session est facultatif. */ }

    const source = resultats.querySelector('[data-source-partage]').dataset.sourcePartage;
    const cases = [...resultats.querySelectorAll('[data-case-partage]')];
    const actifs = new Set();
    for (const etiquette of cases) {
      const casePartage = etiquette.querySelector('input');
      etiquette.hidden = !actif;
      casePartage.checked = coches.has(casePartage.value);
      if (casePartage.checked) actifs.add(casePartage.value);
    }
    const total = coches.size;
    const horsFiltre = total - actifs.size;
    exportClasse.hidden = Boolean(source) || (actif && total > 0);
    commencer.setAttribute('aria-pressed', String(actif));
    commencer.textContent = actif ? 'Masquer la sélection' : 'Sélectionner des compétences à partager';
    formulaire.hidden = !actif;
    raccourci.hidden = !actif;
    raccourci.querySelector('a').textContent = total ? `Aller au partage (${total})` : 'Aller au partage';
    etat.textContent = total ? `${total} compétence${total > 1 ? 's' : ''} cochée${total > 1 ? 's' : ''}${horsFiltre ? ` · ${horsFiltre} hors filtre` : ''}` : 'Cochez les compétences à partager dans la liste.';
    envoyer.disabled = !total;
    envoyer.textContent = total ? `Partager les compétences sélectionnées (${total})` : 'Partager les compétences sélectionnées';
    listeDepliable.hidden = !total;
    valeurs.replaceChildren();
    liste.replaceChildren();
    for (const [cle, libelle] of coches) {
      const champ = document.createElement('input');
      champ.type = 'hidden';
      champ.name = 'competence_partagee';
      champ.value = cle;
      valeurs.append(champ);
      const ligne = document.createElement('li');
      const etiquette = document.createElement('label');
      const casePartage = document.createElement('input');
      casePartage.type = 'checkbox';
      casePartage.checked = true;
      casePartage.value = cle;
      casePartage.dataset.libelle = libelle;
      etiquette.append(casePartage, ' ' + libelle);
      ligne.append(etiquette);
      liste.append(ligne);
    }
  }
  function retourCourant(destination) {
    const retour = new URL(recherche.action);
    retour.search = new URLSearchParams(new FormData(recherche));
    retour.hash = 'partager-competences';
    const chemin = new URL(destination, document.baseURI);
    chemin.searchParams.set('retour', retour.pathname + retour.search + retour.hash);
    return chemin;
  }
  function cocher(event) {
    const choix = event.target;
    if (!choix.matches('input[data-libelle]')) return;
    if (choix.checked) {
      const titre = choix.closest('[data-source-partage]')?.querySelector('h2')?.textContent;
      coches.set(choix.value, titre ? `${choix.dataset.libelle} · ${titre}` : choix.dataset.libelle);
    } else coches.delete(choix.value);
    const depuisRecapitulatif = liste.contains(choix);
    actualiser();
    if (depuisRecapitulatif) (liste.querySelector('input') || commencer).focus();
  }

  commencer.addEventListener('click', () => {
    actif = !actif;
    actualiser();
    if (actif) (resultats.querySelector('[data-case-partage] input') || recherche.elements.q).focus();
  });
  resultats.addEventListener('change', cocher);
  liste.addEventListener('change', cocher);
  resultats.addEventListener('petits-pas:rubriques-actualisees', actualiser);
  exportClasse.addEventListener('click', () => { exportClasse.href = retourCourant(exportClasse.href); });
  formulaire.addEventListener('submit', () => {
    formulaire.setAttribute('action', retourCourant(formulaire.getAttribute('action')));
  });
  window.addEventListener('pageshow', actualiser);
  partage.querySelector('[data-commandes-partage]').hidden = false;
  actualiser();
})();
