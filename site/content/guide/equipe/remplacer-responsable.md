+++
title = "Remplacer un responsable de classe"
description = "Créer le remplacement et terminer l’ancienne affectation dans une même opération."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["remplacer", "remplacement", "responsable", "titulaire", "classe", "continuité"]
prerequis = "Le responsable à remplacer est actif et un autre membre actif peut prendre sa fonction."
depart = "Gérer l’école → Équipe pédagogique → membre responsable"
statut = "disponible"
+++

## Étapes

1. Sous l’affectation responsable concernée, choisir la personne dans
   **Remplacer par**.
2. Ajouter un motif si utile.
3. Sélectionner **Remplacer le responsable**, puis confirmer.

{{< capture-guide src="captures/guide/equipe/remplacer-responsable.png" alt="Formulaire de remplacement du responsable fictif d’une classe" caption="Le remplaçant et le motif sont choisis avant l’opération atomique de remplacement." >}}

## Résultat attendu

Petits Pas attribue d’abord la responsabilité au remplaçant, puis termine
l’affectation précédente. Ces deux changements appartiennent à une même
transaction : l’application ne laisse pas volontairement la classe sans
responsable entre les deux.

Les contributions antérieures restent attribuées à leurs auteurs. Les droits de
l’ancien responsable cessent avec son affectation ; le nouveau reçoit les
droits complets de responsable dans cette classe.

## Limites et refus

- Seul un responsable peut être remplacé par ce parcours.
- La personne choisie doit être un autre membre actif de l’école et ne pas être
  déjà affectée activement à cette classe.
- Cette opération crée un remplacement sans date de fin. Pour un remplacement
  temporaire planifié, attribuer plutôt une fonction responsable avec une date
  de fin, en veillant à la continuité de responsabilité.
- L’historique des deux affectations et le motif sont conservés.

Voir [Terminer ou suspendre une affectation]({{< relref "terminer-suspendre-affectation.md" >}}).
