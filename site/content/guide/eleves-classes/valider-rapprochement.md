+++
title = "Valider un rapprochement avec un dossier existant"
description = "Décider nominativement si une identité importée correspond à un élève déjà connu."
fiche = true
categorie = "eleves-classes"
publics = ["direction"]
intentions = ["rapprochement", "doublon", "homonyme", "dossier existant", "fusion", "valider"]
prerequis = "Un ajout a détecté une ou plusieurs correspondances ; vous exercez la fonction de direction."
depart = "Gérer l’école → classe · ajouter des enfants → Rapprochements à valider"
statut = "disponible"
+++

## Étapes

1. Comparer l’identité proposée, l’année de naissance et chaque dossier
   candidat.
2. Vérifier, lorsqu’elle est indiquée, la dernière classe connue.
3. Sélectionner **Valider ce dossier nominativement** uniquement pour le bon
   dossier.

## Résultat attendu

Le dossier retenu est réactivé si nécessaire et reçoit la scolarité proposée
lorsqu’il n’en possède pas pour cette année. La décision est journalisée et un
accès contrôlé à la continuité du parcours est créé ; aucun second élève n’est
créé.

## Limites et refus

- Le responsable qui a importé la liste ne valide pas lui-même le
  rapprochement : la décision appartient à la direction.
- Il n’y a jamais de fusion automatique sur le seul nom, ni de fusion générale
  de deux dossiers arbitraires.
- La validation est refusée si la demande a déjà été traitée, si le dossier ne
  fait pas partie des candidats, ou s’il appartient déjà à une autre classe
  pour la même année.
- En cas de doute, ne pas valider : vérifier l’identité hors de l’application
  selon les procédures de l’école.

Voir les [règles de continuité et de confidentialité]({{< relref "/roles/situations/" >}}).
