+++
title = "Décider du second facteur dans l’école et aider une personne qui l’a perdu"
description = "Choisir pour quelles fonctions le second facteur est exigé ou retiré, et réinitialiser celui d’une personne qui n’a plus son téléphone."
fiche = true
categorie = "equipe"
publics = ["direction"]
intentions = ["second facteur", "deux facteurs", "obligatoire", "exiger", "politique de l’école", "réinitialiser", "téléphone perdu", "code de secours", "sécurité", "équipe"]
prerequis = "Vous exercez la direction de l’école ; l’hébergeur a activé le second facteur (sinon la rubrique « Second facteur » n’apparaît pas dans Gérer l’école)."
depart = "Gérer l’école → Second facteur ; Gérer l’école → Équipe pédagogique → Personnes"
statut = "disponible"
+++

## À quoi cela sert

Le **second facteur** est un code à six chiffres, affiché par une application sur
le téléphone de chaque personne, qui s’ajoute au mot de passe. Les personnes
concernées le configurent elles-mêmes, à partir de leur page **Mon compte**
(voir la [fiche destinée à toute l’équipe]({{< relref "/guide/equipe/second-facteur/" >}})).

Deux niveaux décident de qui doit l’utiliser :

- **l’hébergeur** de l’application fixe un cadre pour toutes les écoles qu’il
  héberge ;
- **la direction de l’école** peut, dans ce cadre, l’exiger pour davantage de
  fonctions, ou le retirer à certaines.

L’école ne peut jamais assouplir ce que l’hébergeur impose, ni rouvrir ce qu’il a
retiré.

## Choisir pour qui il est exigé

1. Ouvrir **Gérer l’école**, puis **Second facteur**.
2. S’il existe un cadre fixé par l’hébergeur, il est rappelé en haut de la page.
   Les choix qui iraient à son encontre sont **grisés**.
3. Dans « Le second facteur est **obligatoire** pour », choisir jusqu’à quelle
   fonction il est exigé. Chaque choix inclut ceux qui précèdent : *La direction*,
   puis *… et les responsables de classe*, puis *… et les enseignants associés*,
   puis *… et les contributeurs*, jusqu’à *Toutes les personnes de l’école*.
4. Dans « Il est **retiré** (non proposé) pour », choisir au besoin les fonctions
   pour lesquelles il ne sera pas proposé du tout. Par défaut : personne.
5. Sélectionner **Enregistrer**.

Pour toutes les autres fonctions, il reste **facultatif** : chaque personne peut
le configurer si elle le souhaite.

## Résultat attendu

La rubrique **Effet actuel dans l’école** indique combien de personnes sont
soumises à l’obligation et combien l’ont déjà configuré. Les personnes concernées
voient un bandeau les invitant à le faire.

- Une personne déjà membre dispose d’un **délai** (14 jours par défaut, réglé par
  l’hébergeur) qui commence à son premier accès après la décision. Passé ce
  délai, elle ne peut plus que le configurer ou se déconnecter.
- Une personne qui rejoint l’école par invitation est conduite à le configurer
  **dès sa première connexion**, sans délai.
- Une personne rattachée à **plusieurs écoles** est soumise à l’obligation dès
  qu’une seule de ces écoles l’exige pour sa fonction.

## Avant d’exiger le second facteur

- Prévenir l’équipe à l’avance : chacun doit disposer d’un téléphone et, si
  possible, d’une application d’authentification.
- Rappeler de **noter les codes de secours** au moment de la configuration : ils
  évitent de solliciter la direction à chaque perte de téléphone.
- S’assurer que la direction est **joignable** : c’est elle qui réinitialise le
  second facteur des autres personnes (voir ci-dessous).

## Réinitialiser le second facteur d’une personne

À faire quand une personne n’a plus son téléphone **et** n’a plus ses codes de
secours.

1. Ouvrir **Gérer l’école**, puis **Équipe pédagogique**, puis la vue
   **Personnes**.
2. Sur la fiche de la personne, ouvrir **Second facteur de** son prénom.
3. Sélectionner **Réinitialiser le second facteur**.

**Avant cela, s’assurer qu’il s’agit bien de la personne** (en face à face ou par
téléphone) : réinitialiser le second facteur d’un compte sur la foi d’un simple
message ouvrirait la porte à quelqu’un qui connaîtrait le mot de passe.

### Résultat attendu

Une confirmation s’affiche. La clé de la personne et ses codes de secours sont
supprimés. Elle se connecte ensuite avec son mot de passe seul, puis configure de
nouveau son second facteur : immédiatement s’il est obligatoire pour sa fonction,
quand elle le souhaite sinon. L’opération est consignée dans le journal de
l’école.

### Limites

- Le bouton n’apparaît que pour une personne **qui a configuré** un second
  facteur.
- On ne réinitialise **pas le sien**, ni celui d’une personne qui exerce la
  **direction**, dans cette école comme dans une autre : cela revient à
  l’hébergeur de l’application.
- La réinitialisation **ne lève jamais l’obligation**.
- Les sessions que la personne aurait déjà ouvertes sur un autre appareil ne sont
  pas fermées par cette opération.
- Une personne qui doit changer de téléphone alors que le second facteur lui est
  imposé passe par la même réinitialisation.
