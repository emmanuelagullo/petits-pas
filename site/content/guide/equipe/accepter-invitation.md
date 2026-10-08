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
3. Saisir deux fois un mot de passe d’au moins douze caractères. Le formulaire
   refuse un mot de passe trop courant, composé uniquement de chiffres ou trop
   proche du nom d’utilisateur ou du nom, et indique ce qu’il faut corriger.
4. Sélectionner **Créer mon compte et rejoindre l’école**.

## Si un compte existe déjà

Lorsqu’un compte utilise déjà l’adresse de l’invitation, le formulaire demande le
nom d’utilisateur et le mot de passe de ce compte. Sélectionner **Accepter
l’invitation** : après authentification, l’école est ajoutée au même compte, aucune
seconde identité n’est créée.

## Résultat attendu

La page confirme que le compte est activé et membre de l’école. Sélectionner
**Revenir à la connexion**, puis **Entrer** avec vos identifiants : l’acceptation
ne connecte pas automatiquement.

- Si la direction avait **préparé une fonction**, la page liste les **fonctions
  conservées à l’acceptation**, avec leur classe, leurs dates et, pour chacune,
  « accessible maintenant » ou « pas encore accessible ou plus active : vérifiez
  avec la direction ». Une fonction future attend sa date de début ; une classe en
  préparation attend son activation. Le courriel décrit l’état à l’envoi : une
  fonction modifiée, retirée, suspendue ou terminée depuis ne conserve pas ses
  anciens droits.
- Sinon, la direction peut à présent attribuer une fonction. Tant que ce n’est pas
  fait, la connexion affiche : « Votre compte existe, mais aucune fonction ne vous
  a encore été attribuée dans une classe. Contactez la direction de votre
  école. » Cette appartenance seule n’ouvre pas l’application pédagogique.

Si l’hébergeur ou la direction de l’école exige un
[second facteur]({{< relref "/guide/equipe/second-facteur/" >}}) pour cette
fonction, il est à configurer dès la première connexion.

## Limites et refus

- L’adresse associée au compte existant doit correspondre à celle de
  l’invitation, sans distinction de majuscules.
- Un lien expiré, révoqué, déjà accepté ou altéré affiche seulement qu’il n’est
  plus utilisable, sans révéler l’adresse destinataire.
- Le nom d’utilisateur doit être libre et le mot de passe respecter les règles
  ci-dessus.
- Avec un compte existant, un mot de passe erroné compte comme un échec de
  connexion : après plusieurs essais manqués, la page demande de patienter (voir
  la fiche de dépannage de connexion).
- Ne pas transmettre son mot de passe à la direction : chaque compte reste
  individuel.

En cas d’oubli, voir
[Réinitialiser son mot de passe]({{< relref "reinitialiser-mot-de-passe.md" >}}).

Pour une première observation, suivre [Vos premiers pas après une invitation]({{< relref "/guide/service/premiers-pas" >}}).
