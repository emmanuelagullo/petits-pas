(() => {
  "use strict";

  const MIO = 1024 * 1024;
  const LIMITE_BRUTE = 25 * MIO;
  const REGLES = {
    trace: { dimension: 600, qualite: 0.8, qualiteMinimale: 0.7, objectif: 100000 },
    couverture: { dimension: 800, qualite: 0.82, qualiteMinimale: 0.72, objectif: 200000 },
  };

  function annoncer(champ, texte, erreur = false) {
    let etat = champ.parentElement.querySelector("[data-etat-image-privee]");
    if (!etat) {
      etat = document.createElement("span");
      etat.dataset.etatImagePrivee = "";
      etat.setAttribute("role", "status");
      etat.className = "aide";
      champ.insertAdjacentElement("afterend", etat);
    }
    etat.textContent = texte;
    etat.classList.toggle("erreur", erreur);
  }

  function verrouiller(formulaire, verrouille) {
    formulaire?.querySelectorAll('button[type="submit"], input[type="submit"]')
      .forEach((bouton) => { bouton.disabled = verrouille; });
  }

  async function encoder(champ, fichier) {
    const famille = champ.dataset.imagePrivee || "trace";
    const regle = REGLES[famille] || REGLES.trace;
    const image = await createImageBitmap(fichier, { imageOrientation: "from-image" });
    const rapport = Math.min(1, regle.dimension / Math.max(image.width, image.height));
    const largeur = Math.max(1, Math.round(image.width * rapport));
    const hauteur = Math.max(1, Math.round(image.height * rapport));
    const toile = document.createElement("canvas");
    toile.width = largeur;
    toile.height = hauteur;
    const contexte = toile.getContext("2d", { alpha: false });
    contexte.fillStyle = "#fff";
    contexte.fillRect(0, 0, largeur, hauteur);
    contexte.drawImage(image, 0, 0, largeur, hauteur);
    image.close();
    const produire = (qualite) => new Promise((resolve, reject) => {
      toile.toBlob(
        (resultat) => resultat ? resolve(resultat) : reject(new Error("Encodage impossible")),
        "image/jpeg", qualite,
      );
    });
    let blob;
    for (let qualite = regle.qualite; qualite >= regle.qualiteMinimale; qualite -= 0.02) {
      blob = await produire(Math.max(qualite, regle.qualiteMinimale));
      if (blob.size <= regle.objectif) break;
    }
    return new File([blob], `${fichier.name.replace(/\.[^.]*$/, "") || "image"}.jpg`, {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  }

  document.addEventListener("change", async (evenement) => {
    const champ = evenement.target.closest("input[type=file][data-image-privee]");
    if (!champ || !champ.files?.length) return;
    const fichier = champ.files[0];
    champ.setCustomValidity("");
    if (fichier.size > LIMITE_BRUTE) {
      champ.value = "";
      champ.setCustomValidity("L’image dépasse 25 Mio.");
      annoncer(champ, "L’image dépasse 25 Mio : choisissez un autre fichier.", true);
      champ.reportValidity();
      return;
    }
    if (!("createImageBitmap" in window) || !("DataTransfer" in window)) {
      annoncer(champ, "L’image sera automatiquement allégée lors de son enregistrement.");
      return;
    }
    const formulaire = champ.form;
    verrouiller(formulaire, true);
    annoncer(champ, "Préparation de l’image…");
    try {
      const prepare = await encoder(champ, fichier);
      const transfert = new DataTransfer();
      transfert.items.add(prepare);
      champ.files = transfert.files;
      const ko = Math.max(1, Math.round(prepare.size / 1024));
      annoncer(champ, `Image prête à être envoyée (${ko} Ko).`);
    } catch (_erreur) {
      annoncer(champ, "L’image sera automatiquement allégée lors de son enregistrement.");
    } finally {
      verrouiller(formulaire, false);
    }
  });
})();
