+++
title = "Ajouter de nouveaux élèves à une classe"
description = "Coller une liste d’élèves et créer leur scolarité sans fusionner automatiquement les dossiers ressemblants."
fiche = true
categorie = "eleves-classes"
publics = ["responsable", "direction"]
intentions = ["élève", "ajouter", "importer", "liste", "classe", "niveau", "naissance"]
prerequis = "Vous êtes responsable de cette classe, ou membre de la direction."
depart = "Classe → Gérer les enfants, ou Gérer l’école → classe · ajouter des enfants"
statut = "disponible"
+++

## Étapes

1. Choisir le niveau proposé par défaut pour la classe.
2. Dans **Nouveaux élèves**, coller une ligne par enfant.
3. Utiliser au choix un simple prénom ou le format
   `Prénom ; Nom ; Niveau ; Année de naissance`.
4. Sélectionner **Ajouter ces enfants**.

Le niveau écrit sur une ligne remplace le niveau par défaut. Les tabulations
sont acceptées comme séparateurs à la place des points-virgules.

{{< capture-guide src="captures/guide/classes/composition.png" alt="Composition d’une classe avec ses élèves fictifs et les actions de gestion" caption="La composition permet de corriger un niveau, déplacer, retirer ou ouvrir le parcours d’un élève fictif." >}}

## Résultat attendu

Le message final distingue les dossiers créés des rapprochements à faire
valider. Chaque nouveau dossier reçoit une scolarité dans la classe et pour son
année scolaire.

## Limites et conséquences

- Une ligne vide est ignorée. Le prénom est l’information minimale nécessaire.
- Si une identité ressemble à un dossier déjà connu, aucun doublon ni aucune
  fusion n’est décidé automatiquement : une demande est créée pour la
  direction.
- Un responsable peut créer les nouveaux élèves de sa classe mais ne peut pas
  récupérer librement un dossier situé ailleurs dans l’école.
- Le collage ne remplace pas la composition existante de la classe ; il ajoute
  des élèves.

Pour une correspondance détectée, poursuivre avec
[Valider un rapprochement de dossier]({{< relref "valider-rapprochement.md" >}}).
