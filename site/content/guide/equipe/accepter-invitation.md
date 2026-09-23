+++
title = "Créer ou rattacher son compte invité"
description = "Utiliser l’invitation reçue pour rejoindre l’école avec une identité individuelle."
fiche = true
categorie = "equipe"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["invitation", "accepter", "créer compte", "rejoindre école", "compte existant", "mot de passe"]
prerequis = "Vous disposez du lien reçu par courriel ou transmis par la direction ; il n’a pas expiré ni déjà servi."
depart = "Courriel d’invitation → lien Rejoindre l’école"
statut = "disponible"
+++

## Si aucun compte n’utilise encore cette adresse

1. Ouvrir le lien d’invitation.
2. Choisir un nom d’utilisateur et renseigner prénom et nom.
3. Saisir deux fois un mot de passe d’au moins douze caractères, conforme aux
   indications du formulaire.
4. Sélectionner **Créer mon compte et rejoindre l’école**.

## Si un compte existe déjà

Le formulaire demande le nom d’utilisateur et le mot de passe de ce compte.
Après authentification, l’école est ajoutée au même compte : aucune seconde
identité n’est créée.

## Résultat attendu

La page confirme que le compte est activé et membre de l’école. Revenir ensuite
à la connexion. Tant que la direction n’a attribué ni responsabilité d’école ni
fonction dans une classe, cette appartenance seule n’ouvre pas l’application
pédagogique.

## Limites et refus

- L’adresse associée au compte existant doit correspondre à celle de
  l’invitation, sans distinction de majuscules.
- Un lien expiré, révoqué, déjà accepté ou altéré affiche seulement qu’il n’est
  plus utilisable, sans révéler l’adresse destinataire.
- Le nom d’utilisateur doit être disponible et le mot de passe doit satisfaire
  les validateurs Django.
- Ne pas transmettre son mot de passe à la direction : chaque compte reste
  individuel.

En cas d’oubli, voir
[Réinitialiser son mot de passe]({{< relref "reinitialiser-mot-de-passe.md" >}}).
