+++
title = "Protéger son compte avec un code de vérification"
description = "Ajouter à son mot de passe un code qui change toutes les trente secondes, produit par une application, un petit jeton ou un logiciel de l’ordinateur, et savoir quoi faire en cas de perte."
fiche = true
categorie = "equipe"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["second facteur", "deux facteurs", "code de vérification", "application d’authentification", "générateur de codes", "jeton", "extension de navigateur", "code de secours", "téléphone perdu", "appareil perdu", "changer de téléphone", "changer d’appareil", "sécurité", "compte"]
prerequis = "L’hébergeur de votre installation a activé cette fonction, et elle est proposée pour votre fonction ; vous disposez d’un moyen de produire des codes à six chiffres : application sur un téléphone ou une tablette, petit jeton, ou à défaut logiciel sur votre ordinateur."
depart = "Mon compte → Authentification à deux facteurs"
statut = "disponible"
+++

## À quoi cela sert

Un mot de passe peut être deviné, aperçu par-dessus l’épaule, ou réutilisé
ailleurs puis volé. Le **second facteur** ajoute une deuxième vérification : un
code à six chiffres, qui change toutes les trente secondes et que produit un
**générateur de codes**. Sans ce code, connaître votre mot de passe ne suffit
plus pour entrer.

Petits Pas contient des observations sur des enfants : l’effort se fait une seule
fois, puis prend quelques secondes à chaque connexion. Selon l’hébergeur et la
direction de l’école, le second facteur est **facultatif** ou **obligatoire**
pour votre fonction.

## Où produire les codes ?

Plusieurs solutions conviennent ; aucun matériel particulier n’est imposé :

- **une application sur un téléphone ou une tablette** (par exemple FreeOTP,
  Aegis ou Google Authenticator), qui n’a pas besoin d’internet, ou un petit
  **jeton** matériel compatible ;
- **à défaut d’autre appareil**, un logiciel sur votre ordinateur : extension de
  navigateur, ou gestionnaire de mots de passe qui sait générer ces codes.

Un appareil distinct est un plus, surtout conseillé aux personnes qui gèrent
l’école (direction) : quelqu’un qui s’empare de l’ordinateur n’y trouve pas aussi
les codes. Pour les autres, un logiciel sur l’ordinateur reste nettement
préférable à un mot de passe seul (mot de passe deviné, volé ou réutilisé
ailleurs). Il ne protège pas d’une personne qui utiliserait votre session
ouverte, et il est à éviter sur un poste partagé.

## Configurer le second facteur

1. Préparer le générateur de codes choisi.
2. Dans Petits Pas, ouvrir **Mon compte**, puis, dans la rubrique
   « Authentification à deux facteurs », sélectionner **Configurer**.
3. Ajouter le compte dans le générateur de codes : **scanner le carré noir et
   blanc** affiché à l’écran (le « QR code »). Si le scan est impossible, par
   exemple parce que le générateur est sur ce même poste, saisir à la main la
   clé écrite sous le carré.
4. Si votre connexion date de plus de cinq minutes, saisir aussi votre mot de
   passe. Saisir le code à six chiffres que le générateur affiche, puis
   sélectionner **Activer**.
5. La page **Vos codes de secours** apparaît. Noter les dix codes de préférence
   sur papier (ils ne sont affichés qu’une fois), puis sélectionner **J’ai noté
   mes codes**.

**Mon compte** indique ensuite qu’un second facteur est configuré.

## Se connecter ensuite

1. Saisir le nom d’utilisateur et le mot de passe comme d’habitude.
2. Sur la page **Vérification en deux étapes**, saisir le code que le générateur
   affiche à cet instant, puis sélectionner **Valider**.

Tant que ce code n’est pas saisi, aucune session n’est ouverte.

Si le code est refusé alors qu’il semble bon : attendre le code suivant (chacun
ne sert qu’une fois) et vérifier que l’heure de l’appareil se règle
**automatiquement**. Après plusieurs essais manqués, la page demande de patienter.

## Si vous n’avez plus votre générateur de codes

Utiliser un **code de secours** à la place du code à six chiffres (chacun ne sert
qu’une fois ; l’écran indique combien il en reste). Pour en générer de nouveaux :
**Mon compte** → **Gérer** → saisir un code actuel → **Générer de nouveaux
codes** ; les anciens cessent alors de fonctionner.

Sans générateur ni code de secours, demander à la direction de l’école de
**réinitialiser** votre second facteur (voir la
[fiche de la direction]({{< relref "/guide/equipe/second-facteur-ecole/" >}})).
Une personne qui exerce elle-même la direction s’adresse à la personne qui
héberge l’application. La réinitialisation ferme vos sessions ouvertes : vous vous
reconnectez avec votre mot de passe seul, puis vous configurez de nouveau le
second facteur.

## Changer de téléphone ou d’appareil

Garder l’ancien générateur jusqu’à ce que le nouveau soit configuré. Si le second
facteur est **facultatif** pour vous : **Mon compte** → **Gérer**, saisir un code
actuel, **Retirer le second facteur**, puis **Configurer** avec le nouveau
générateur. S’il est **obligatoire**, demander à la direction de le réinitialiser
puis le configurer de nouveau.

## Quand il devient obligatoire

Un bandeau indique le nombre de jours restants pour le configurer ; passé ce
délai, seules la page de configuration et la déconnexion restent accessibles. Un
compte créé par invitation le configure dès sa première connexion, sans délai. Il
ne peut alors plus être retiré. Une personne rattachée à plusieurs écoles y est
soumise dès qu’une seule l’exige pour sa fonction.

## Limites et sécurité

- Si **Mon compte** n’affiche pas la rubrique « Authentification à deux
  facteurs », elle n’est pas proposée pour votre fonction ou n’est pas activée
  (le programme installé sur un seul poste ne la propose pas).
- Ne communiquer à personne ni les codes du générateur, ni les codes de secours,
  à conserver ailleurs que sur le générateur (sur papier, par exemple).
- Réinitialiser son mot de passe ne supprime pas le second facteur.
