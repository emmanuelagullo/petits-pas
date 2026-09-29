(() => {
  const catalogue = JSON.parse(document.getElementById("icones-apercu").textContent);
  document.querySelectorAll("form[data-presentation]").forEach(form => {
    const mode = form.querySelector('[name="mode"]');
    const icone = form.querySelector('[name="icone"]');
    const apercu = form.querySelector('[data-apercu-icone]');
    const actualiser = () => {
      const editable = mode.value === "remplacer";
      form.querySelectorAll('[name="icone"], [name="photo"], [name="photo-clear"]').forEach(champ => {
        champ.disabled = !editable;
      });
      const texte = form.querySelector('[name="texte"]');
      if (texte) texte.readOnly = !editable;
      const aide = form.querySelector('[data-aide-champs]');
      if (aide) aide.hidden = editable;
      if (apercu) {
        const url = catalogue[icone.value];
        apercu.hidden = !editable || !url;
        if (url) {
          apercu.querySelector("img").src = url;
          apercu.querySelector("img").alt = icone.selectedOptions[0].textContent;
        }
      }
    };
    mode.addEventListener("change", actualiser);
    if (icone) icone.addEventListener("change", actualiser);
    actualiser();
  });
})();
