+++
title = "Comprendre un refus d’affectation ou de remplacement"
description = "Préserver une équipe active, une responsabilité continue et un historique attribué."
fiche = true
categorie = "depannage"
publics = ["direction"]
intentions = ["affectation refusée", "dernier responsable", "remplacement impossible", "suspension", "membre inactif", "fonction"]
prerequis = "Vous exercez la fonction de direction et consultez l’équipe de la bonne école."
depart = "Gérer l’école → Équipe pédagogique"
statut = "disponible"
+++

## Membre absent du formulaire

Seules les appartenances actives de l’école peuvent recevoir une fonction. Une
invitation acceptée crée cette appartenance ; une invitation seulement envoyée
ne suffit pas. Vérifier aussi les dates et l’état de l’appartenance.

## Dernier responsable impossible à terminer

La fin normale est bloquée tant qu’aucun autre responsable ne garantit la
continuité. Utiliser **Remplacer le responsable** : la nouvelle affectation est
créée avant que l’ancienne soit terminée, dans une même transaction.

## Aucun remplaçant proposé

Le candidat doit être un autre membre actif et ne pas posséder déjà une
affectation active dans cette classe. Inviter ou rattacher d’abord la personne,
ou examiner ses affectations actuelles.

## Suspension d’urgence refusée

Le motif est obligatoire. Contrairement à une fin normale, la suspension peut
laisser temporairement la classe sans responsable ; Petits Pas ouvre alors une
anomalie de gouvernance que la direction doit traiter.

## Droits encore absents après attribution

Vérifier que la classe est active, que la date de début est atteinte, que la
date de fin n’est pas dépassée et que l’affectation n’est ni terminée ni
suspendue. Se déconnecter n’est normalement pas nécessaire : les autorisations
sont recalculées sur chaque requête.

Voir [Attribuer une fonction]({{< relref "/guide/equipe/attribuer-fonction.md" >}}),
[Remplacer un responsable]({{< relref "/guide/equipe/remplacer-responsable.md" >}})
et [Terminer ou suspendre une affectation]({{< relref "/guide/equipe/terminer-suspendre-affectation.md" >}}).
