+++
title = "Créer puis activer une classe"
description = "Préparer une classe pour une année scolaire, lui attribuer un responsable et l’ouvrir aux usages pédagogiques."
fiche = true
categorie = "eleves-classes"
publics = ["direction"]
intentions = ["classe", "créer", "activer", "préparation", "année scolaire", "responsable"]
prerequis = "Vous exercez la fonction de direction dans l’école."
depart = "Gérer l’école → Créer une classe"
statut = "disponible"
+++

## Créer la classe

1. Saisir son nom usuel.
2. Indiquer l’année scolaire sous la forme `2027-2028` : la seconde année doit
   suivre immédiatement la première.
3. Sélectionner **Créer et ajouter les enfants**.

La classe est créée **en préparation**. Vous pouvez déjà en composer l’effectif,
mais elle n’ouvre pas encore les droits pédagogiques ordinaires.

{{< capture-guide src="captures/direction.png" alt="Page de gestion de l’école fictive avec ses classes" caption="La gestion de l’école fictive, générée automatiquement depuis la démonstration." >}}

## Attribuer un responsable et activer

1. Dans **Équipe pédagogique**, attribuer la fonction **Responsable de classe**
   à un membre actif pour cette classe.
2. Revenir dans **Gérer l’école**.
3. Sous la classe en préparation, sélectionner **Activer la classe**, puis
   confirmer.

## Résultat attendu

La classe apparaît comme active. Les personnes affectées peuvent désormais y
accéder selon leur fonction ; la direction conserve sa vue administrative sans
recevoir automatiquement l’accès au suivi pédagogique.

## Limites et refus

- Une classe sans responsable actif ne peut pas être activée : l’interface
  indique d’abord d’attribuer cette fonction.
- Une classe de même nom pour la même année scolaire est refusée.
- L’interface ne permet actuellement ni de renommer, ni d’archiver, ni de
  supprimer une classe.

Voir les [règles détaillées des rôles et affectations]({{< relref "/roles/" >}}).
