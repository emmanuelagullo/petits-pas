+++
title = "Institutions et hébergement"
description = "Architecture, maîtrise des données et possibilités d'auto-hébergement."
+++

Petits Pas est une application Django dont l'interface web s'appuie sur HTMX.
Deux façons de travailler existent : le mode hébergé, accessible à plusieurs
personnes par navigateur, et l’utilisation sur un appareil, dans le navigateur ou avec le programme téléchargé. Plusieurs comptes peuvent s’y relayer. Les profils ci-dessous précisent leurs usages et leurs données.

Le projet ne fournit pas d’hébergement centralisé pour les écoles.
Cette page distingue donc l'architecture déjà exercée des garanties qui restent
à établir avant un pilote ou une production.

Pour choisir un parcours, consulter [Démarrer]({{< relref "/demarrer/" >}}).
La [protection des données]({{< relref "/proteger-donnees/" >}}) concerne les deux façons de travailler.

Plusieurs personnes peuvent recevoir les [droits de gestion de l’école]({{< relref "/guide/equipe/gerer-droits-ecole/" >}})
avec leurs comptes personnels. Les passations conservent une relève sans
interruption ni fin prévue. Les accès pédagogiques restent liés aux classes ;
la récupération du second facteur d’une direction relève de l’hébergeur.

## Choisir un profil

| Profil | Où sont les données ? | Données admises | Finalité |
| --- | --- | --- | --- |
| [Démonstration publique]({{< relref "/demonstration/" >}}) | Sur un serveur distant, effacées lors de son arrêt | Fictives uniquement, visibles par les visiteurs | Découvrir librement l'interface |
| [Navigateur sur cet appareil](#application-dans-le-navigateur) | Base et médias dans le stockage local du navigateur | Fictives uniquement pour la publication actuelle | Essai personnel, sans synchronisation entre appareils |
| [Programme sur cet appareil](#mode-autonome-local) | SQLite, médias et clé dans un paquet persistant sur le poste | Préparer la protection des données avec l’école ; les essais sur appareil recueillent les retours | Usage sur un poste, sans partage entre ordinateurs |
| Atelier pédagogique hébergé | PostgreSQL et stockage S3 persistants sur un serveur distant | Fictives uniquement | Recueillir des retours dans la durée |
| Pilote ou production hébergés | PostgreSQL et stockage S3 persistants sur un serveur distant | Réelles, seulement après validation des garanties nécessaires | Usage partagé d'une école ou d'une collectivité |

Le profil d'atelier refuse de démarrer sans marqueurs explicites et ne peut pas
être simultanément déclaré éphémère. La démonstration refuse quant à elle une
base PostgreSQL ou un bucket S3 afin de ne jamais être confondue avec un
environnement persistant.

## Mode hébergé

### Architecture persistante

Un profil PostgreSQL avec médias privés sur un système de fichiers persistant
est aussi documenté dans `DEPLOIEMENT.org` et exercé en CI. Il exige une
sauvegarde coordonnée de la base et des médias ; S3 n’est pas obligatoire.


Le profil hébergé persistant utilise un serveur d’application Python,
PostgreSQL, un stockage objet privé compatible S3 et une terminaison HTTPS
fournie par la plateforme d’hébergement.

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

### Sauvegarde et reprise du mode hébergé

Le profil persistant dispose de procédures pour :

- sauvegarder PostgreSQL ;
- inventorier et sauvegarder les médias du stockage objet ;
- produire un manifeste et un paquet coordonnant ces deux ensembles ;
- restaurer ce paquet dans des cibles distinctes ;
- vérifier la cohérence de la reprise restaurée.

La CI exerce cette chaîne avec PostgreSQL et MinIO dans des services jetables.
Ce test vérifie qu'une reprise est réalisable ; il ne transforme pas pour autant
une sauvegarde effectuée en ligne en instantané parfaitement atomique et ne
remplace pas les exercices réguliers de l'hébergeur. Aucune commande de
restauration de la base partagée n’est proposée dans l’interface de direction.

## Mode autonome local

### Fonctionnement et installation

Le programme autonome embarque Django et ouvre l’interface dans une fenêtre
PyWebView. Django écoute sur `127.0.0.1` pendant l’utilisation ; il n’y a pas
de service distant à administrer. Le courrier est désactivé. Sous Linux, le
paquet de données se trouve par défaut dans
`~/.local/share/petits-pas/paquet-autonome/` (ou dans `$XDG_DATA_HOME`) ; sous
Windows, dans `%LOCALAPPDATA%\petits-pas\paquet-autonome`. Le chemin peut être
choisi au lancement. Le programme et les données sont installés séparément :
une mise à jour du programme conserve le paquet de données.

Les archives Ubuntu et Windows sont construites séparément. Sous Ubuntu, GTK,
WebKit2 et les bibliothèques natives de génération PDF doivent être
disponibles. Les archives Linux ne constituent pas des paquets Guix. Les
[fiche de téléchargement]({{< relref "/guide/local/telecharger-programme.md" >}})
centralise les archives publiques ; les [fiches pratiques du mode local]({{< relref "/guide/local/" >}}) décrivent
l’installation et les sauvegardes ; le [README du dépôt](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/README.md)
précise les commandes de construction, les dépendances et les limites.

### Sauvegarde et reprise sur le poste

Une personne disposant de la direction peut exporter dans l’interface un ZIP
contenant la base SQLite, les médias et la clé, puis vérifier et restaurer ce
ZIP. La restauration ferme la session et conserve le paquet précédent dans un
dossier distinct ; elle n’en produit pas automatiquement un ZIP. Les sauvegardes
doivent être conservées dans un emplacement protégé, distinct du poste et du
paquet de travail. Le mode local ne dispense pas de qualifier la protection
physique du poste, les sauvegardes et les règles d’accès avant tout pilote avec
des données réelles.

La [comparaison des écrans de direction]({{< relref "/guide/local/" >}})
montre pourquoi le bouton **Sauvegardes locales** est absent en mode hébergé.

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

Les photos des traces communes peuvent être utilisées dans plusieurs carnets
sans être rendues publiques. Les images ajoutées par une école ou une classe
pour illustrer les compétences ou la couverture restent également privées.
Les petits dessins fournis avec l'application sont des ressources publiques,
distinctes de ces photos. Les sauvegardes doivent conserver la base et les
fichiers d'images pour retrouver les traces et la présentation des carnets.

Les parcours d'utilisation sont décrits dans le
[Guide pratique]({{< relref "/guide/carnets/personnaliser-presentation/" >}}).

### Authentification à deux facteurs

Un second facteur par code temporaire (six chiffres, trente secondes) peut
s'ajouter au mot de passe. Il est **facultatif et absent par défaut** : il
n'existe que si l'hébergeur installe une extension de dépendances
(`requirements-2fa.txt`) et renseigne une clé de chiffrement. Sans cela, rien ne
change pour personne. Le programme installé sur un seul poste ne le propose pas.

L'hébergeur fixe un cadre pour toutes ses écoles : le 2FA peut être rendu
obligatoire jusqu'à une fonction donnée, ou retiré à partir d'une fonction. Dans
ce cadre, la direction de chaque école peut l'exiger pour davantage de
fonctions, jamais pour moins ; une obligation reçue ne peut pas être abaissée.

La clé secrète de chaque personne est chiffrée en base avec une clé propre au
déploiement. **Perdue ou remplacée sans précaution, cette clé rend illisibles
tous les secrets enregistrés** : elle doit être conservée avec les autres
secrets d'exploitation, et peut être renouvelée sans réinscrire personne en
gardant l'ancienne à la suite de la nouvelle. En cas de téléphone perdu, trois
recours existent : dix codes de secours à usage unique remis à chaque personne,
la réinitialisation par la direction de l'école pour les fonctions inférieures
à la sienne, et une commande d'exploitation pour tout compte, direction
comprise.

Le détail des variables, de la clé et de la procédure figure dans la
[documentation de déploiement](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/DEPLOIEMENT.org).
Les parcours pour les équipes et la direction sont dans le
[guide pratique]({{< relref "/guide/equipe/second-facteur/" >}}).

### Garanties restant à consolider

Avant tout usage avec des données réelles, il reste notamment à consolider :

- l'intégration des comptes individuels aux procédures réelles d'arrivée, de
  changement de fonction et de départ des personnes ;
- la revue systématique de la couverture des autorisations et de leur
  journalisation, y compris face aux requêtes forgées et aux accès
  inter-écoles ;
- pour le second facteur : la fermeture des sessions déjà ouvertes lors d'une
  réinitialisation, et un changement de téléphone en autonomie lorsque le second
  facteur est obligatoire ;
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
  navigateur épinglé, sur ordinateur et pour plusieurs parcours mobiles ;
- des contrôles structurels et l'absence de débordement horizontal sur les
  pages capturées.

Les détails et limites des profils sont suivis dans la
[documentation de déploiement](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/DEPLOIEMENT.org)
et la
[documentation de l'atelier pédagogique](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/ATELIER-PEDAGOGIQUE.org).

## Restrictions sur les changements de référentiel

Les changements après saisies sont interdits par défaut. Le gestionnaire de
l’application doit les permettre explicitement pour l’année, puis la direction
pour son école, puis le responsable ou la direction pour une classe. L’exception
de classe se referme après un changement. Une autorisation de base dans le
catalogue reste distincte de cette permission exceptionnelle.

L’opération d’exploitation `regler_changements_referentiels` demande une
révision consultée et une confirmation explicite d’ouverture. Les opérations
web majeures demandent une réauthentification, avec limitation des tentatives.
Les adoptions et parcours existants restent conservés lors du retrait d’une
permission. La démonstration fictive ouvre seulement la permission supérieure
pour permettre les essais ; ce réglage n’est pas une recommandation pour une
école réelle.

## Application dans le navigateur

Django/Pyodide fonctionne dans un Worker ; les données restent dans OPFS/IndexedDB
sur l’appareil. ZIP et droits locaux sont communs au programme autonome. La limite
actuelle est de 64 Mio avant compression. Depuis #PWA11, les médias confirmés
sont lus à la demande dans OPFS ; SQLite et les transferts ZIP utilisent encore
la mémoire. Vérifier la version effectivement publiée.
Voir le [parcours navigateur]({{< relref "/guide/local/essayer-navigateur" >}})
et les [vérifications sur appareil]({{< relref "/guide/local/verifier-appareil" >}}).
