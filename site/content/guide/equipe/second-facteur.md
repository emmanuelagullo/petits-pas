+++
title = "Protéger son compte avec un code de vérification"
description = "Ajouter à son mot de passe un code qui change toutes les trente secondes, et savoir quoi faire si l’on perd son téléphone."
fiche = true
categorie = "equipe"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["second facteur", "deux facteurs", "code de vérification", "application d’authentification", "code de secours", "téléphone perdu", "changer de téléphone", "sécurité", "compte"]
prerequis = "L’hébergeur de votre installation a activé cette fonction, et elle est proposée pour votre fonction ; vous disposez d’un téléphone sur lequel installer une application d’authentification."
depart = "Mon compte → Authentification à deux facteurs"
statut = "disponible"
+++

## À quoi cela sert

Un mot de passe peut être deviné, aperçu par-dessus l’épaule, ou réutilisé
ailleurs puis volé. Le **second facteur** ajoute une
deuxième vérification : un code à six chiffres, affiché par une application sur
votre téléphone et qui change toutes les trente secondes. Sans ce code, connaître
votre mot de passe ne suffit plus pour entrer.

Petits Pas contient des observations sur des enfants et leurs photos. Protéger
les comptes qui y accèdent vaut donc un petit effort, qui se fait une seule fois
puis ne prend que quelques secondes à chaque connexion.

Selon la décision de l’hébergeur et de la direction de l’école, cette
vérification est **facultative** ou **obligatoire** pour votre fonction.

## Configurer le second facteur

1. Installer sur le téléphone une application d’authentification, par exemple
   FreeOTP, Aegis ou Google Authenticator. Elle n’a pas besoin de connexion
   internet pour afficher les codes.
2. Dans Petits Pas, ouvrir **Mon compte**, puis, dans la rubrique
   « Authentification à deux facteurs », sélectionner **Configurer**.
3. Dans l’application, ajouter un compte puis **scanner le carré noir et blanc**
   affiché à l’écran (le « QR code »). Si le scan est impossible, saisir à la
   main la clé écrite sous le carré.
4. Saisir dans Petits Pas le code à six chiffres que l’application affiche, puis
   sélectionner **Activer**.
5. La page **Vos codes de secours** apparaît. Noter les dix codes sur papier ou
   dans un gestionnaire de mots de passe, puis sélectionner **J’ai noté mes
   codes**.

## Résultat attendu

**Mon compte** indique qu’un second facteur est configuré. Les codes de secours
ne sont **affichés qu’une seule fois** : si la page est fermée avant de les avoir
notés, il faudra en générer de nouveaux (voir plus bas).

## Se connecter ensuite

1. Saisir le nom d’utilisateur et le mot de passe comme d’habitude.
2. Sur la page **Vérification en deux étapes**, saisir le code que l’application
   affiche à cet instant, puis sélectionner **Valider**.

Tant que ce code n’est pas saisi, aucune session n’est ouverte : une personne qui
ne connaîtrait que votre mot de passe n’accède à rien.

### Si le code est refusé alors qu’il semble bon

- Chaque code ne sert **qu’une seule fois** : attendre que l’application en
  affiche un nouveau, puis réessayer.
- Vérifier que l’heure du téléphone se règle **automatiquement** : un téléphone
  dont l’heure est décalée d’une trentaine de secondes ou plus peut produire des
  codes refusés.
- Après plusieurs essais manqués, la page demande de patienter. Il faut alors
  ressaisir le mot de passe depuis la page de connexion.

## Si vous n’avez plus votre téléphone

Utiliser un **code de secours** : à la place du code à six chiffres, saisir l’un
des codes notés lors de la configuration. Les majuscules, les minuscules, les
tirets et les espaces n’ont pas d’importance.

- Chaque code de secours ne sert **qu’une seule fois**. L’écran indique combien
  il en reste.
- Quand il en reste peu, en générer de nouveaux : **Mon compte** →
  **Gérer** → saisir un code actuel de l’application →
  **Générer de nouveaux codes**. Les anciens cessent alors de fonctionner.
- Si vous n’avez ni téléphone ni code de secours, demander à la direction de
  l’école de **réinitialiser** votre second facteur (voir la
  [fiche de la direction]({{< relref "/guide/equipe/second-facteur-ecole/" >}})).
  Une personne qui exerce elle-même la direction s’adresse à la personne qui
  héberge l’application. Après la réinitialisation, vous vous connectez avec votre
  mot de passe seul, puis vous configurez de nouveau le second facteur.

## Changer de téléphone

Si possible, garder l’ancien téléphone jusqu’à ce que le nouveau soit configuré.

- Si le second facteur est **facultatif** pour vous : **Mon compte** → **Gérer**,
  saisir un code actuel, **Retirer le second facteur**, puis **Configurer**
  depuis le nouveau téléphone.
- S’il est **obligatoire** pour vous, il ne peut pas être retiré par vous-même :
  demander à la direction de le réinitialiser, puis le configurer sur le nouveau
  téléphone.

## Quand le second facteur devient obligatoire

Si l’hébergeur ou la direction de l’école l’exige pour votre fonction :

- un bandeau indique le nombre de jours qu’il vous reste pour le configurer ;
- passé ce délai, seules la page de configuration et la déconnexion restent
  accessibles, jusqu’à ce que le second facteur soit en place ;
- un compte créé par invitation doit le configurer dès sa première connexion,
  sans délai ;
- il n’est alors plus possible de le retirer.

## Limites et sécurité

- La fonction dépend de l’installation. Si **Mon compte** n’affiche pas la
  rubrique « Authentification à deux facteurs », elle n’est pas proposée pour
  votre fonction ou n’est pas activée. Le programme installé sur un seul poste
  ne la propose pas.
- Ne communiquer à personne ni les codes de l’application, ni les codes de
  secours : personne n’a de raison de vous les demander.
- Conserver les codes de secours ailleurs que sur le téléphone, par exemple sur
  papier dans un endroit fermé.
- Réinitialiser son mot de passe ne supprime pas le second facteur : le code
  reste demandé à la connexion.
- Une personne rattachée à plusieurs écoles est soumise à l’obligation dès
  qu’une seule de ces écoles l’exige pour sa fonction.
