(() => {
  const normaliser = (texte) => texte
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

  document.querySelectorAll("[data-guide-search]").forEach((recherche) => {
    const champ = recherche.querySelector("[data-guide-query]");
    const fiches = [...recherche.querySelectorAll("[data-guide-entry]")];
    const compteur = recherche.querySelector("[data-guide-count]");
    const vide = recherche.querySelector("[data-guide-empty]");

    const filtrer = () => {
      const termes = normaliser(champ.value).trim().split(/\s+/).filter(Boolean);
      let visibles = 0;

      fiches.forEach((fiche) => {
        const texte = normaliser(fiche.dataset.guideText || fiche.textContent);
        const correspond = termes.every((terme) => texte.includes(terme));
        fiche.hidden = !correspond;
        if (correspond) visibles += 1;
      });

      compteur.textContent = `${visibles} fiche${visibles > 1 ? "s" : ""} pratique${visibles > 1 ? "s" : ""}`;
      vide.hidden = visibles !== 0;
    };

    champ.addEventListener("input", filtrer);
  });
})();
