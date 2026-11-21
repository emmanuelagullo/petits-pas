+++
title = "Consulter, imprimer ou télécharger une grille de suivi"
description = "Lire les états de la classe pour une ou plusieurs compétences."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["grille", "suivi", "imprimer", "PDF", "classe", "compétence"]
prerequis = "Vous pouvez consulter le suivi de la classe. Le téléchargement PDF est réservé au responsable."
depart = "Classe → Saisir pour toute la classe → Grille de suivi"
statut = "disponible"
+++

## Étapes

1. Dans **Saisir pour toute la classe**, choisir **Grille de suivi**. Pour
   examiner une seule compétence, l’ouvrir puis choisir **Voir la grille de suivi**.
2. Lire le résumé au-dessus du tableau. Par défaut, la grille de classe
   affiche les compétences observées pendant l’année.
3. Ouvrir **Filtres** pour choisir les élèves puis les **Compétences** dans
   l’arbre. Cocher une rubrique ou une sous-rubrique sélectionne toute sa
   branche. Décocher une compétence permet d’affiner cette sélection.
   **Afficher uniquement les compétences cochées** permet de la relire.
   La recherche déplie les résultats sans modifier les cases cochées.
4. Choisir **Appliquer les filtres**.
5. Le responsable peut **Télécharger le PDF** ou, dans l’application navigateur,
   **Préparer l’impression / PDF**. **Préparer une édition** reprend la sélection
   pour produire des carnets ou des cartes à découper.

{{< capture-guide src="captures/guide/observer/grille-classe.png" alt="Grille fictive avec les élèves en lignes et les compétences en colonnes" caption="La grille regroupe les compétences par rubrique et sous-rubrique. Les symboles et les couleurs indiquent les états." >}}

Les élèves sont en lignes. Les colonnes sont regroupées par rubrique et
sous-rubrique. En mode compact, leur numéro renvoie au libellé complet.
Sur un écran étroit, choisir **Une compétence à la fois** dans **Mise en page**.
Le nom d’un élève ouvre son suivi lorsqu’il est accessible. **Retour à la
grille** retrouve sa ligne et les filtres utilisés.
Le PDF répartit les grandes grilles sur plusieurs tableaux, avec les élèves
et les en-têtes répétés. La grille d’une compétence garde une colonne pour
les notes de séance sur papier.

## Observations et période

Une compétence figure dans le résultat dès qu’au moins un élève retenu
correspond au filtre. Pour une période donnée, choisir **Observations sur une
période** ou **Réussites constatées sur une période**. Choisir un raccourci
(**Depuis la rentrée**, les 7, 14 ou 30 derniers jours, **Semaine en cours**,
ou **Depuis le dernier bilan de la classe** si un bilan visible existe), ou
**Dates personnalisées**. Pour les dates personnalisées, saisir deux dates ou
une date de début et une durée. Les deux bornes sont incluses.

**Automatique** privilégie les compétences observées. Une rubrique ou une
compétence cochée peut faire apparaître des compétences encore sans observation.
Pour les afficher indépendamment de toute observation, choisir **Toutes les
compétences suivies**. La période choisit les colonnes. Les couleurs restent
celles du suivi annuel.

Les cases distinguent **À observer** (blanc, ○), **En cours** (orange, ◐),
**Réussi** (vert, ✓), **Hors du suivi** (gris, —) et **État non retrouvé** (?).
Les élèves hors du suivi d’une compétence ciblée restent visibles mais ne sont
pas comptés comme en attente d’observation.

## Reprendre son travail

Le bandeau résume les filtres appliqués. La grille de classe retrouve les
derniers critères de cette classe et de cette année pendant la session.
**Réinitialiser** retire ces critères. Ouvrir la grille d’une compétence depuis
sa fiche ne remplace pas les critères de la grille de classe.

Le document est réservé à l’équipe pédagogique.
Voir la distinction entre **voir le suivi** et **générer** dans la
[matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
