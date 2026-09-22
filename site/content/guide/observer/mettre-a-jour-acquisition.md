+++
title = "Mettre à jour l’acquisition d’un élève"
description = "Faire passer une compétence de « pas encore observée » à « réussie », « en cours », puis revenir à l’état initial."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["acquisition", "compétence", "réussie", "en cours", "observation", "élève"]
prerequis = "L’élève est actif dans une classe à laquelle vous êtes affecté. Seul le responsable peut changer l’état."
depart = "Accueil → classe → élève"
statut = "disponible"
+++

## Étapes

1. Ouvrir la classe, puis choisir l’élève.
2. Si nécessaire, limiter la liste à la petite, moyenne ou grande section.
3. Sélectionner une compétence une première fois pour la marquer **réussie**.
4. La sélectionner une deuxième fois pour la marquer **en cours**.
5. La sélectionner une troisième fois pour revenir à **pas encore observée**.

La date affichée à droite de la compétence est actualisée à chaque changement.

{{< capture-guide src="captures/acquisitions.png" alt="Liste des acquisitions d’une élève fictive, organisée par domaines" caption="La fiche d’un élève fictif, produite automatiquement depuis la démonstration." >}}

## Résultat attendu

Le symbole et le libellé accessibles de la ligne reflètent immédiatement le
nouvel état, sans recharger toute la page. Le carnet et les grilles utilisent
ensuite cet état.

## Limites et refus

- Un enseignant associé peut consulter cet écran mais ne peut pas changer
  l’état. Une tentative directe est refusée, même si la ligne reste visible.
- Un contributeur n’ouvre pas le suivi complet : il utilise la page de
  contribution ciblée pour ajouter ses propres traces.
- Une affectation terminée ne donne plus accès à l’élève actif.

Voir les [règles détaillées des rôles]({{< relref "/roles/" >}}) et les
[situations de cumul ou de fin d’affectation]({{< relref "/roles/situations/" >}}).
