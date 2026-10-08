+++
title = "Comprendre un refus de connexion ou d’invitation"
description = "Réagir à un mot de passe oublié, un compte sans fonction ou un lien d’invitation inutilisable."
fiche = true
categorie = "depannage"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["connexion refusée", "mot de passe incorrect", "invitation invalide", "invitation expirée", "compte", "email"]
prerequis = "Vous disposez du message affiché et, pour une invitation, du lien complet reçu."
depart = "Page de connexion ou page Rejoindre l’école"
statut = "disponible"
+++

## « Nom d’utilisateur ou mot de passe incorrect »

1. Utiliser le nom d’utilisateur, qui n’est pas nécessairement l’adresse
   électronique.
2. Vérifier les majuscules et la disposition du clavier.
3. Utiliser **Mot de passe oublié ?** plutôt que demander ou partager le secret
   d’une autre personne.

Ce même message peut apparaître lorsque l’identité est correcte mais ne possède
plus aucune appartenance à une école. La direction doit alors vérifier le
rattachement et les périodes.

## « Aucune fonction ne vous a encore été attribuée »

Le message complet est : « Votre compte existe, mais aucune fonction ne vous a
encore été attribuée dans une classe. Contactez la direction de votre école. »
Le mot de passe est bon et la personne est bien membre de l’école, mais elle n’a
ni responsabilité d’école ni fonction dans une classe : l’application pédagogique
reste fermée. Demander à la direction de lui
[attribuer une fonction]({{< relref "/guide/equipe/attribuer-fonction.md" >}}).
Pour une personne que l’on invite, la fonction peut être
[préparée dès l’invitation]({{< relref "/guide/equipe/inviter-membre.md" >}}).

## « Trop de tentatives de connexion »

Après plusieurs essais manqués avec le même identifiant depuis la même adresse
(cinq par défaut), la page bloque cet identifiant pendant quelques minutes (quinze
par défaut) depuis cette adresse. Les autres identifiants ne sont pas touchés.

1. Attendre la fin du blocage plutôt que réessayer au hasard.
2. Si le mot de passe est oublié, demander une réinitialisation : voir
   [Réinitialiser son mot de passe]({{< relref "/guide/equipe/reinitialiser-mot-de-passe.md" >}}).
3. Si l’installation n’envoie pas de courriels, la page invite à contacter la
   direction de l’école.

Plusieurs personnes derrière une même adresse (par exemple un établissement)
n’en sont pas affectées tant qu’elles utilisent des identifiants différents.

## Le code de vérification est refusé

Cela concerne les personnes qui ont configuré un
[second facteur]({{< relref "/guide/equipe/second-facteur/" >}}).

1. Attendre que l’application affiche un **nouveau** code : chacun ne sert
   qu’une fois.
2. Vérifier que l’heure de l’appareil qui produit les codes est réglée
   **automatiquement**.
3. Après plusieurs essais manqués, la page demande de patienter ; ressaisir
   alors le mot de passe depuis la page de connexion.
4. Sans le générateur de codes (téléphone perdu, jeton cassé, poste changé),
   saisir un **code de secours** à la place.
5. Sans générateur ni code de secours, demander à la direction de réinitialiser
   le second facteur. Pour la direction elle-même, s’adresser à l’hébergeur.

## « Cette invitation n’est plus utilisable »

Le lien a expiré, a été révoqué, a déjà servi ou ne contient pas le bon jeton.
Pour préserver la confidentialité, la page ne précise pas lequel de ces cas
s’applique et ne révèle pas l’adresse invitée. Demander une nouvelle invitation
à la direction.

## Compte existant refusé pendant l’acceptation

Le compte doit porter la même adresse électronique que l’invitation. Utiliser
ses propres identifiants ; si le mot de passe est oublié, le réinitialiser puis
rouvrir le lien d’invitation encore valable.

## Courriel absent

- vérifier les courriers indésirables et l’adresse saisie ;
- pour une invitation qui vient d’être créée, la direction peut utiliser le
  lien de secours affiché une seule fois ;
- si l’invitation a expiré, en créer une nouvelle plutôt que tenter de modifier
  son adresse.

Les réponses de réinitialisation restent volontairement identiques qu’un compte
existe ou non pour l’adresse, afin de ne pas fournir un annuaire de comptes.

Voir [Réinitialiser son mot de passe]({{< relref "/guide/equipe/reinitialiser-mot-de-passe.md" >}})
et [Créer ou rattacher son compte invité]({{< relref "/guide/equipe/accepter-invitation.md" >}}).
