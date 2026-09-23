// Ajoute un bouton « afficher »/« masquer » à côté de chaque champ de
// mot de passe, pour permettre de vérifier sa saisie avant de valider.
// Aucune dépendance : reste dans l'esprit sobre du projet.
(function () {
  function creerBouton(champ) {
    var bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "bouton-oeil";
    bouton.textContent = "afficher";
    bouton.setAttribute("aria-label", "Afficher le mot de passe");
    bouton.setAttribute("aria-pressed", "false");
    bouton.addEventListener("click", function () {
      var enClair = champ.type === "text";
      champ.type = enClair ? "password" : "text";
      bouton.textContent = enClair ? "afficher" : "masquer";
      bouton.setAttribute("aria-pressed", enClair ? "false" : "true");
      bouton.setAttribute(
        "aria-label",
        enClair ? "Afficher le mot de passe" : "Masquer le mot de passe"
      );
    });
    return bouton;
  }

  function ajouterBoutons() {
    document.querySelectorAll('input[type="password"]').forEach(function (champ) {
      if (champ.dataset.bascule === "prete") {
        return;
      }
      champ.dataset.bascule = "prete";
      var enveloppe = document.createElement("span");
      enveloppe.className = "champ-mot-de-passe";
      champ.parentNode.insertBefore(enveloppe, champ);
      enveloppe.appendChild(champ);
      enveloppe.appendChild(creerBouton(champ));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ajouterBoutons);
  } else {
    ajouterBoutons();
  }
})();
