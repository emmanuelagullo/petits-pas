+++
title = "Attribuer une fonction dans une classe"
description = "Donner à un membre un périmètre pédagogique précis, éventuellement limité dans le temps."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["attribuer", "fonction", "affectation", "responsable", "enseignant associé", "contributeur", "date de fin"]
prerequis = "La personne est membre actif de l’école et la classe existe."
depart = "Gérer l’école → Équipe pédagogique → Classes"
statut = "disponible"
+++

## Étapes

1. Repérer la classe, puis ouvrir **Ajouter une personne à cette classe**.
2. Choisir la personne et sa fonction : **Responsable de classe**, **Enseignant associé** ou
   **Contributeur**.
3. Ajouter si nécessaire une date de fin et un motif.
4. Sélectionner **Attribuer**.

{{< capture-guide src="captures/roles/diane/gouvernance-secours.png" alt="Formulaire d’attribution d’une fonction et anomalies de gouvernance fictives" caption="Attribution des fonctions et contrôle de gouvernance dans la démonstration." >}}

## Résultat attendu

L’affectation apparaît dans la classe avec la personne, sa fonction, ses dates et
son état. Ses droits sont calculés à partir de cette fonction, pour cette classe
seulement et pendant la période active.

La vue **Personnes** permet la même opération dans l’autre sens avec
**Attribuer une fonction à…** : la personne est alors déjà sélectionnée.

Une affectation responsable active résout l’anomalie signalant une classe sans
responsable. Elle permet ensuite à la direction d’activer une classe encore en
préparation.

## Limites et conséquences

- Seuls les membres actifs de la même école sont proposés.
- Une fonction reçue dans une classe ne se propage pas aux autres classes.
- **Enseignant associé** permet la consultation et la contribution mais pas la
  décision sur les états ni la génération finale ; **Contributeur** n’ouvre que
  la contribution ciblée.
- La fonction de direction est une responsabilité d’école distincte ; elle ne
  s’attribue pas avec ce formulaire.
- Une date de fin rend automatiquement l’affectation inactive après cette date,
  sans effacer ses contributions historiques.

Voir la [présentation des rôles]({{< relref "/roles/" >}}) et les
[situations illustrées]({{< relref "/roles/situations/" >}}).
