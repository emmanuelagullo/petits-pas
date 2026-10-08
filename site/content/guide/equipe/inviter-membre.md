+++
title = "Inviter un nouveau membre"
description = "Envoyer un lien à usage unique pour créer un compte ou rattacher un compte existant à l’école, avec si l’on veut une fonction préparée."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["inviter", "membre", "équipe", "courriel", "email", "lien", "révoquer", "préparer une fonction", "pré-attribuer", "fonction à l’invitation", "annuler une invitation"]
prerequis = "Vous exercez la fonction de direction et connaissez l’adresse électronique individuelle de la personne."
depart = "Gérer l’école → Équipe pédagogique → Inviter une personne"
statut = "disponible"
+++

## Étapes

1. Ouvrir **Inviter une personne**, puis saisir son adresse électronique.
2. Facultatif : choisir une **Classe** et une **Fonction** (responsable de
   classe, enseignant associé ou contributeur) pour **préparer une fonction**
   avant l’acceptation. Voir « Préparer une fonction » plus bas. Ces choix
   n’apparaissent que s’il existe une classe de l’année en cours ou d’une année à
   venir.
3. Sélectionner **Créer l’invitation**.
4. Vérifier le message : il indique si le courriel a été envoyé, si son envoi
   a échoué ou si cette installation fonctionne sans courriel. Il rappelle la
   fonction préparée, le cas échéant.
5. Si nécessaire, copier le lien affiché à cet instant et le transmettre par
   un canal approprié.

{{< capture-guide src="captures/roles/diane/invitations.png" alt="Invitations de l’équipe fictive, avec leurs états" caption="Invitations fictives en attente et révoquées, issues du scénario automatique." >}}

## Résultat attendu

L’invitation apparaît dans le volet **Invitations en attente ou récentes** avec son état, son expiration et, le cas
échéant, la fonction préparée. Elle est valable sept jours et son lien n’est
utilisable qu’une fois. Lorsque l’envoi est configuré, le courriel explique comment
créer un compte ou rattacher un compte existant, et présente les fonctions
préparées avec leur classe, leur année et leurs dates.

Le lien de secours complet n’est affiché qu’après la création puis retiré de la
session ; la liste ne permet pas de le retrouver ultérieurement.

## Préparer une fonction

Sans fonction préparée, la personne peut créer son compte, mais n’accède pas à
l’application pédagogique tant que la direction ne lui a pas attribué de fonction,
une fois le compte créé.

Avec une fonction préparée, elle est **conservée à l’acceptation** de
l’invitation. Les droits dépendent alors de son état, de ses dates et de
l’activation de la classe : une fonction future attend sa date de début, une
classe en préparation attend son activation. L’écran d’acceptation indique, pour
chaque fonction, si elle est accessible tout de suite.

Avant l’acceptation, la fonction n’ouvre **aucun droit**. Elle apparaît avec la
pastille **Invitation en cours** dans l’**Équipe pédagogique** (vue par classe) et
dans **Collaborateurs**. Seule la direction y voit l’adresse électronique de la
personne invitée ; les autres collaborateurs lisent « personne invitée ».

Pour renoncer à la fonction avant l’acceptation : sur sa ligne, ouvrir **Gérer**,
puis **Annuler la pré-attribution**. L’invitation reste valable ; la personne
rejoindra l’école sans cette fonction.

## Révoquer avant utilisation

Déplier **Invitations en attente ou récentes**. Tant que l’invitation est en attente et non expirée, sélectionner **Révoquer**.
Le lien ne permettra alors plus de rejoindre l’école, et la fonction préparée est
annulée en même temps. Il en va de même quand une invitation expire sans avoir été
acceptée : rien d’autre n’est à faire.

## Limites et refus

- Une personne déjà membre actif de l’école ne peut pas être invitée à nouveau.
- Une seconde invitation valable pour la même adresse est refusée.
- Un échec ou une désactivation du courriel n’annule pas l’invitation : le lien
  affiché reste utilisable.
- Une invitation expirée, révoquée ou acceptée ne peut pas être réutilisée ; il
  faut en créer une nouvelle si nécessaire.
- Sans fonction préparée, l’invitation crée uniquement une appartenance : la
  direction attribue ensuite une fonction (voir
  [Attribuer une fonction]({{< relref "attribuer-fonction.md" >}})). L’invitation ne
  donne jamais la direction.
- La fonction ne se prépare qu’à la création de l’invitation. Pour une invitation
  déjà créée, annuler la fonction préparée, ou révoquer l’invitation et en créer
  une nouvelle.
- Le courriel présente les fonctions à l’envoi ; des changements ultérieurs ne le
  réécrivent pas. L’état au moment de l’acceptation fait foi.

Voir [Créer ou rattacher son compte invité]({{< relref "accepter-invitation.md" >}}).
