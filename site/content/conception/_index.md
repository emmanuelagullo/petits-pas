+++
title = "Documents de conception"
description = "Le modèle, la politique et les scénarios de référence des rôles et autorisations."
+++

Cette rubrique rassemble les documents ayant servi à concevoir puis à
implémenter le modèle de comptes, rôles et autorisations de Petits Pas. Elle
s'adresse aux personnes qui souhaitent approfondir les règles métier, leur
traduction en autorisations et les scénarios de validation.

Le **code et les tests décrivent toujours l'état effectivement implémenté**.
Ces documents conservent également la chronologie et le contexte des décisions :
une formulation prospective ou un audit portant sur un ancien commit doit donc
être lu à la date indiquée dans le document.

## État du chantier

Les incréments `#A1` à `#A9` ont introduit les comptes individuels, les
appartenances aux écoles, les responsabilités de direction, les affectations
datées aux classes, le moteur central d'autorisation, le cloisonnement des
lectures et mutations, ainsi que l'audit des principales actions et sorties de
données. `#A10` fournit une équipe fictive riche pour exercer ces situations ;
`#A11` conserve les documents ayant guidé le chantier.

Le plan d'implémentation ci-dessous reste donc un **audit historique de la
situation antérieure à `#A1`**, et non une description du code courant. Les
autres documents expriment les décisions métier de référence ; une divergence
avec le comportement observé doit être signalée et traitée explicitement.

## Les quatre documents de référence

1. [Modèle des identités et des affectations]({{< relref "documents/modele-identites-et-affectations.org" >}})
   définit les personnes, appartenances, responsabilités, affectations,
   périodes et invariants métier.
2. [Politique d'autorisation détaillée]({{< relref "documents/politique-autorisation.org" >}})
   indique qui peut effectuer chaque opération, dans quel périmètre et sous
   quelles conditions.
3. [Matrice des autorisations et scénarios de tests]({{< relref "documents/matrice-autorisations.org" >}})
   donne la lecture normative et les principaux cas autorisés ou refusés.
4. [Audit initial et plan d'implémentation]({{< relref "documents/plan-implementation-autorisations.org" >}})
   décrit l'état antérieur au chantier et le découpage qui a conduit à
   l'implémentation des autorisations.

Ces textes constituent la documentation approfondie. Une présentation plus
directe et illustrée, destinée en priorité aux équipes pédagogiques, sera
ajoutée séparément afin de ne pas imposer ce niveau de détail lors d'une
première visite.
