+++
title = "Inviter un nouveau membre"
description = "Envoyer un lien à usage unique pour créer un compte ou rattacher un compte existant à l’école."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["inviter", "membre", "équipe", "courriel", "email", "lien", "révoquer"]
prerequis = "Vous exercez la fonction de direction et connaissez l’adresse électronique individuelle de la personne."
depart = "Gérer l’école → Équipe pédagogique → Inviter un membre"
statut = "disponible"
+++

## Étapes

1. Saisir l’adresse électronique de la personne.
2. Sélectionner **Créer l’invitation**.
3. Vérifier le message : il indique si le courriel a été envoyé, si son envoi
   a échoué ou si cette installation fonctionne sans courriel.
4. Si nécessaire, copier le lien affiché à cet instant et le transmettre par
   un canal approprié.

{{< capture-guide src="captures/roles/diane/invitations.png" alt="Invitations de l’équipe fictive, avec leurs états" caption="Invitations fictives en attente et révoquées, issues du scénario automatique." >}}

## Résultat attendu

L’invitation apparaît dans la liste avec son état et son expiration. Elle est
valable sept jours et son lien n’est utilisable qu’une fois. Lorsque l’envoi est
configuré, le courriel explique comment créer un compte ou rattacher un compte
existant.

Le lien de secours complet n’est affiché qu’après la création puis retiré de la
session ; la liste ne permet pas de le retrouver ultérieurement.

## Révoquer avant utilisation

Tant que l’invitation est en attente et non expirée, sélectionner **Révoquer**.
Le lien ne permettra alors plus de rejoindre l’école.

## Limites et refus

- Une personne déjà membre actif de l’école ne peut pas être invitée à nouveau.
- Une seconde invitation valable pour la même adresse est refusée.
- Un échec ou une désactivation du courriel n’annule pas l’invitation : le lien
  affiché reste utilisable.
- Une invitation expirée, révoquée ou acceptée ne peut pas être réutilisée ; il
  faut en créer une nouvelle si nécessaire.
- L’invitation crée une appartenance à l’école, mais aucun droit pédagogique.
  Une fonction de classe doit ensuite être attribuée séparément.

Voir [Créer ou rattacher son compte invité]({{< relref "accepter-invitation.md" >}}).
