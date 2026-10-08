/* Information uniquement : aucun enregistrement, aucune interruption de formulaire. */
(() => {
  const bandeau = document.getElementById("annonce-maintenance");
  if (!bandeau) return;
  const delai = document.getElementById("delai-maintenance");
  let debut = null;
  function afficher() {
    bandeau.hidden = debut === null;
    if (debut === null) return;
    const secondes = Math.max(0, Math.ceil(debut - Date.now() / 1000));
    delai.textContent = secondes ? `dans ${Math.floor(secondes / 60)} min ${String(secondes % 60).padStart(2, "0")} s` : "très prochainement";
  }
  async function verifier() {
    if (document.hidden) return;
    try {
      const reponse = await fetch(bandeau.dataset.url, {cache: "no-store", signal: AbortSignal.timeout(5000)});
      if (reponse.ok) {
        const annonce = await reponse.json();
        debut = typeof annonce.debut === "number" && Number.isFinite(annonce.debut) ? annonce.debut : null;
      } else { debut = null; }
    } catch (_) { debut = null; }
    afficher();
  }
  verifier();
  setInterval(verifier, 10000);
  setInterval(afficher, 1000);
  document.addEventListener("visibilitychange", verifier);
})();
