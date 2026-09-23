+++
title = "Corriger l’identité ou le niveau d’un élève"
description = "Modifier les informations durables du dossier ou le niveau de sa scolarité courante."
fiche = true
categorie = "eleves-classes"
publics = ["responsable", "direction"]
intentions = ["corriger", "identité", "prénom", "nom", "année de naissance", "niveau", "PS", "MS", "GS"]
prerequis = "Vous êtes responsable de la classe concernée, ou membre de la direction."
depart = "Gérer les enfants → nom de l’élève → Parcours scolaire"
statut = "disponible"
+++

## Corriger l’identité durable

1. Ouvrir le parcours de l’élève.
2. Corriger le prénom, le nom ou l’année de naissance.
3. Sélectionner **Enregistrer l’identité**.

Le prénom est obligatoire. Une année de naissance non numérique est
actuellement interprétée comme une valeur absente.

## Modifier le niveau de l’année

Dans **Composition actuelle de la classe**, choisir PS, MS ou GS sur la ligne de
l’élève. Le changement est envoyé immédiatement lorsque le menu est modifié ;
une confirmation est demandée.

## Résultat attendu

L’identité corrigée est utilisée dans toute l’école. Le niveau, lui, appartient
à la scolarité de l’année et ne réécrit pas les années précédentes.

## Limites et conséquences

- Un responsable n’agit que sur les élèves d’une classe dont il gère
  l’effectif ; la direction peut intervenir à l’échelle de l’école.
- Ne pas créer un nouveau dossier pour corriger une faute : cela séparerait le
  parcours de l’enfant.
- La page ne demande pas la date de naissance complète, seulement l’année.

Voir la [matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
