+++
title = "Pour les DSI et les hébergeurs"
description = "Architecture, maîtrise des données et possibilités d'auto-hébergement."
+++

Petits Pas est une application Django dont l'interface web s'appuie sur HTMX.
Elle est conçue autour de composants courants et remplaçables : un serveur
d'application Python, PostgreSQL pour les données structurées, un stockage
objet privé compatible S3 pour les médias et une terminaison HTTPS fournie par
la plateforme d'hébergement.

Le projet ne propose pas encore un service prêt à recevoir des données réelles.
Cette page distingue donc l'architecture déjà exercée des garanties qui restent
à établir avant un pilote ou une production.

## Architecture du profil persistant

- **Django et Gunicorn** portent les règles métier, les pages HTML et les
  échanges HTMX. Le navigateur n'a pas besoin d'une application monopage ni
  d'un service JavaScript séparé.
- **PostgreSQL** conserve les écoles, classes, élèves, référentiels,
  observations et métadonnées des traces.
- **Un stockage objet S3 privé** conserve les photographies et autres médias.
  Leur accès passe par des adresses signées de durée limitée.
- **La plateforme d'hébergement** assure le routage public et la terminaison
  TLS. L'application interprète explicitement les en-têtes du mandataire
  inverse.
- **Les migrations et fichiers statiques** sont préparés au démarrage selon le
  profil choisi.

Cette séparation évite notamment de placer les médias dans l'image de
l'application ou dans son système de fichiers éphémère.

## Trois profils qui ne doivent pas être confondus

| Profil | Persistance | Données admises | Finalité |
| --- | --- | --- | --- |
| [Démonstration publique]({{< relref "/demonstration/" >}}) | SQLite et médias locaux, effacés lors de l'arrêt du service | Fictives uniquement, visibles par les visiteurs | Découvrir librement l'interface |
| Atelier pédagogique | PostgreSQL et stockage S3 persistants | Fictives uniquement | Recueillir des retours dans la durée |
| Pilote ou production | PostgreSQL et stockage S3 persistants | Réelles, seulement après validation des garanties nécessaires | Usage opérationnel d'une école ou d'une collectivité |

Le profil d'atelier refuse de démarrer sans marqueurs explicites et ne peut pas
être simultanément déclaré éphémère. La démonstration refuse quant à elle une
base PostgreSQL ou un bucket S3 afin de ne jamais être confondue avec un
environnement persistant.

## Déployer et garder la maîtrise

La licence AGPL autorise une école, une collectivité ou un prestataire à
installer, auditer, adapter et exploiter sa propre instance. Une offre
d'hébergement ou d'accompagnement payante demeure possible.

Le dépôt contient les migrations, les dépendances verrouillées, les commandes
de démarrage et la documentation d'exploitation. Le recours à PostgreSQL et à
une interface S3 limite la dépendance à un fournisseur particulier, sans faire
disparaître le travail nécessaire pour qualifier une nouvelle plateforme.

Lorsqu'une version modifiée est proposée aux utilisateurs comme service, les
conditions de l'AGPL leur permettent d'obtenir le code source correspondant.

## Sauvegarde et reprise

Le profil persistant dispose de procédures pour :

- sauvegarder PostgreSQL ;
- inventorier et sauvegarder les médias du stockage objet ;
- produire un manifeste et un paquet coordonnant ces deux ensembles ;
- restaurer ce paquet dans des cibles distinctes ;
- vérifier la cohérence de la reprise restaurée.

La CI exerce cette chaîne avec PostgreSQL et MinIO dans des services jetables.
Ce test vérifie qu'une reprise est réalisable ; il ne transforme pas pour autant
une sauvegarde effectuée en ligne en instantané parfaitement atomique et ne
remplace pas les exercices réguliers de l'hébergeur.

## Protection des données

L'auto-hébergement ne suffit pas, à lui seul, à garantir la conformité d'un
traitement. Celle-ci dépend également des responsabilités, contrats,
habilitations, durées de conservation, sauvegardes et pratiques de chaque
déploiement.

### Socle déjà implémenté

Le socle applicatif ne repose plus sur deux mots de passe partagés. Chaque
personne utilise un compte individuel, relié à une ou plusieurs écoles puis,
selon ses fonctions, à des responsabilités d'école ou à des affectations de
classe datées.

Le serveur réévalue les autorisations au moment de l'action. Une responsabilité
de direction permet d'administrer l'école, mais n'ouvre pas à elle seule le
suivi pédagogique. Les responsables, enseignants associés et contributeurs
reçoivent des capacités différentes, limitées aux classes auxquelles ils sont
affectés. Les sorties sensibles, comme les PDF et les téléchargements de médias
originaux, font l'objet de contrôles et d'événements d'audit spécifiques.

### Garanties restant à consolider

Avant tout usage avec des données réelles, il reste notamment à consolider :

- l'intégration des comptes individuels aux procédures réelles d'arrivée, de
  changement de fonction et de départ des personnes ;
- la revue systématique de la couverture des autorisations et de leur
  journalisation, y compris face aux requêtes forgées et aux accès
  inter-écoles ;
- les politiques de conservation, d'effacement et d'export ;
- la revue de sécurité, l'accessibilité et les conditions d'exploitation ;
- la répartition documentée des responsabilités entre école, collectivité et
  hébergeur.

Ces éléments relèvent à la fois du logiciel, de l'infrastructure et de
l'organisation. Ils ne seront pas présentés comme acquis avant d'avoir été
définis et éprouvés.

Cette implémentation ne dispense pas d'une revue avant pilote. Les [documents
de conception des rôles et autorisations]({{< relref "/conception/" >}})
présentent le modèle métier, la politique détaillée, la matrice de tests et
l'audit initial qui a conduit à ce socle.

## Reproductibilité et intégration continue

La CI vérifie actuellement :

- les dépendances verrouillées et une variante suivant Django 5.2 ;
- les migrations et les tests applicatifs ;
- la syntaxe des scripts de démarrage et d'exploitation ;
- un déploiement complet avec PostgreSQL et MinIO ;
- la sauvegarde puis la restauration dans des cibles temporaires ;
- la construction du site public et la génération de captures fictives dans un
  navigateur épinglé.

Les détails et limites des profils sont suivis dans la
[documentation de déploiement](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/DEPLOIEMENT.org)
et la
[documentation de l'atelier pédagogique](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/ATELIER-PEDAGOGIQUE.org).
