+++
title = "Consulter, imprimer ou télécharger une grille de suivi"
description = "Obtenir la vue de classe d’une compétence, avec les états et une colonne de notes de séance."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["grille", "suivi", "imprimer", "PDF", "classe", "compétence"]
prerequis = "Vous pouvez consulter le suivi de la classe. Le téléchargement PDF est réservé au responsable."
depart = "Classe → Saisir pour toute la classe → compétence → Voir la grille de suivi"
statut = "disponible"
+++

## Étapes

1. Choisir la compétence depuis la saisie collective.
2. Sélectionner **Voir la grille de suivi**.
3. Vérifier le résumé : nombre d’élèves à observer, en cours et en réussite.
4. Utiliser **Imprimer** pour la boîte de dialogue du navigateur, ou
   **Télécharger le PDF** pour conserver un document.

## Résultat attendu

La grille comporte une ligne par élève, une marque dans la colonne correspondant
à son état, et une colonne vierge pour les notes de séance. Le pied précise la
date d’édition et le caractère interne du document.

## Limites et refus

- Responsable et enseignant associé peuvent consulter et imprimer la page.
- La production du PDF utilise le droit de génération : elle est donc réservée
  au responsable. Une URL appelée directement par un autre rôle est refusée.
- La colonne de notes est destinée au papier ; son contenu n’est pas saisi ni
  conservé dans Petits Pas.

Voir la distinction entre **voir le suivi** et **générer** dans la
[matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
