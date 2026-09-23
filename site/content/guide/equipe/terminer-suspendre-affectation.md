+++
title = "Terminer ou suspendre une affectation"
description = "Fermer normalement une fonction ou couper immédiatement ses droits en situation d’urgence."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["terminer", "suspendre", "urgence", "affectation", "droits", "départ", "fin de fonction"]
prerequis = "L’affectation est active et vous exercez la fonction de direction."
depart = "Gérer l’école → Équipe pédagogique → affectation du membre"
statut = "disponible"
+++

## Fin normale

1. Sélectionner **Terminer** sous l’affectation.
2. Confirmer l’action.

L’état devient terminé et la date de fin prend la date du jour. Les droits
cessent, tandis que l’identité, l’affectation et les contributions historiques
restent conservées.

## Suspension d’urgence

1. Saisir obligatoirement le motif d’urgence.
2. Sélectionner **Suspendre en urgence**, puis confirmer.

La suspension coupe immédiatement les droits. Si elle retire le dernier
responsable de la classe, une anomalie de gouvernance est ouverte pour rendre la
situation visible à la direction.

{{< capture-guide src="captures/roles/lea/remplacement.png" alt="Affectation temporaire fictive avec dates et état" caption="Une affectation conserve sa fonction, sa période et son état dans l’historique." >}}

## Limites et conséquences

- La fin normale du dernier responsable est bloquée : utiliser le formulaire de
  remplacement afin que la continuité soit assurée.
- La suspension d’urgence reste possible pour couper un accès sans attendre un
  remplacement, mais exige un motif et peut créer une anomalie à traiter.
- Terminer ou suspendre ne supprime pas les traces créées par la personne.
- Une ancienne URL ou une session existante ne rend pas les droits : les
  autorisations sont recalculées à chaque action selon la période active.

Voir les [situations de remplacement et de fin d’affectation]({{< relref "/roles/situations/" >}}).
