+++
title = "Saisir une compétence pour toute la classe"
description = "Afficher tous les élèves pour mettre à jour rapidement une même compétence."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["classe", "compétence", "saisie groupée", "élèves", "acquisition"]
prerequis = "La classe est active et comporte des élèves. Seul le responsable peut changer les états."
depart = "Accueil → classe → Saisir pour toute la classe"
statut = "disponible"
+++

## Étapes

1. Ouvrir la classe et choisir **Saisir pour toute la classe**.
2. Sélectionner un domaine, puis la compétence observée.
3. Pour chaque élève concerné, sélectionner sa ligne : **réussi**, **en cours**,
   puis **pas encore observé** se succèdent.
4. Utiliser **Changer de compétence** pour poursuivre la séance sur un autre
   apprentissage.

## Résultat attendu

La page conserve la compétence en titre et présente une ligne par élève actif.
Chaque changement est enregistré immédiatement et apparaît aussi dans la fiche
individuelle de l’élève.

## Limites et refus

- L’enseignant associé peut consulter la saisie par classe et la grille, mais
  le changement d’état est réservé au responsable.
- La page signale explicitement une classe sans élève ; elle ne permet pas d’en
  inscrire un.
- Les commentaires et photographies se saisissent depuis la fiche individuelle
  ou la page de contribution, pas depuis cette vue collective.

La [matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}) distingue la
consultation du suivi de la modification des états.
