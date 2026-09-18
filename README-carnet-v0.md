# Carnet de suivi des apprentissages — V0

Un carnet numérique de suivi pour le cycle 1, dans l'esprit d'Iticarnet, qui
ferme fin mai 2027. Cette V0 vise d'abord **une école pilote** : elle est faite
pour être mise rapidement entre les mains d'un enseignant et évoluer à partir
des retours pédagogiques.

Django 5.2/6.1 + HTMX, avec SQLite pour le développement ou la démonstration
et PostgreSQL + stockage objet S3 pour un déploiement persistant. Aucune
dépendance distante n'est nécessaire au moment de l'affichage : HTMX est
embarqué, parce que le wifi des écoles n'est pas fiable.

## Ce qu'elle fait

- Trois écrans de travail : la classe, un enfant, une compétence.
- **Saisie par enfant** : la liste complète du référentiel, filtrable par
  section. Un appui = réussi, deux = en cours, trois = effacé.
- **Saisie éclair** : une compétence observée, toute la classe sur un écran.
- **Parcours longitudinal** : identité durable, scolarités annuelles,
  archivage réversible et plusieurs bilans datés.
- **Traces** : plusieurs commentaires ou photos datés par compétence, chacun
  pouvant être affiché dans le carnet ou conservé uniquement pour l'équipe.
- **Carnet imprimable** : une couverture et des pages de compétences pensées
  pour être données aux parents. La prévisualisation permet de comparer les
  réussites seules, les apprentissages observés ou le référentiel complet.
  Un téléchargement produit à la demande un PDF individuel avec WeasyPrint.
- Deux mots de passe pour l'école, enseignant et direction, comme Iticarnet.
- Import d'une liste d'élèves par copier-coller.

## Ce qu'elle ne fait pas

Volontairement, à ce stade :

- **Un seul état courant par couple enfant-compétence.** Les traces sont
  historiques, mais les changements successifs de l'état « réussi » ou « en
  cours » ne constituent pas encore un journal permettant de reconstruire à
  l'identique chaque ancienne édition.
- Pas d'inscription en ligne : les écoles se créent en ligne de commande.
- Pas de comptes individuels : le mot de passe est partagé par l'équipe. On ne
  sait donc pas qui a saisi quoi.
- Pas d'envoi de carnet aux parents, pas d'espace parent.
- Photos stockées telles quelles, sans redimensionnement.
- Pas encore d'édition collective ni d'archive ZIP pour toute une classe.
- Pas de synthèse de fin de GS, pas d'export ONDE.

La première hypothèse de carnet de la phase 3, ses cas de contrôle et les
questions à soumettre à l'équipe pédagogique sont décrits dans
[`CARNET-REFERENCE.org`](CARNET-REFERENCE.org).

Le parcours de travail — préparation de l'école, saisie quotidienne, bilans,
préparation d'une édition, export et outils internes — est formalisé dans
[`PARCOURS-ENSEIGNANT.org`](PARCOURS-ENSEIGNANT.org). Il distingue ce qui
existe déjà de ce qui est attendu pour la démonstration, le premier essai ou
une évolution ultérieure.

La séparation entre identité de l'élève, scolarités annuelles, bilans et
traces multiples, ainsi que la migration sans perte depuis `0.3`, est définie
dans [`MODELE-LONGITUDINAL.org`](MODELE-LONGITUDINAL.org).

## Démarrer

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock

python manage.py migrate
python manage.py creer_ecole "École maternelle des Tilleuls" --commune "Angoulême"
# notez les deux mots de passe affichés, ils ne sont pas stockés en clair

python manage.py charger_referentiel referentiel/trame-cycle1.yaml
python manage.py runserver
```

`requirements.lock` reproduit les versions Python validées pour la version
courante. `requirements.txt` conserve des plages plus larges afin de permettre
d’autres résolutions compatibles, notamment un futur environnement Guix. La
séparation et ses limites sont détaillées dans `REPRODUCTIBILITE.org`.

Pour voir l'outil rempli avant de le montrer à quelqu'un :

```sh
python manage.py jeu_demo    # une classe de 16 enfants et ~300 observations
```

Les tests couvrent notamment l'accès, le parcours longitudinal, les bilans,
les traces multiples, les PDF, l'isolation entre écoles, les sauvegardes et
restaurations, l'import et le rechargement du référentiel :

```sh
python manage.py test suivi
```

## Intégration continue

Le fichier `.gitlab-ci.yml` exécute automatiquement les contrôles du projet
sur un runner partagé de `gitlab.inria.fr`, avec une base PostgreSQL créée pour
la durée du job :

- tests Django ;
- absence de migration oubliée ;
- validation syntaxique des scripts shell ;
- détection des erreurs d’espacement par Git.

Si un pipeline reste en attente faute de runner, activez un runner partagé dans
`Paramètres > CI/CD > Runners`. Le job utilise les tags `ci.inria.fr` et
`small`. Aucune variable secrète n’est nécessaire pour cette première CI : les
identifiants présents dans le fichier sont réservés à la base éphémère du job.

Après ces contrôles, un second job déploie l’application avec PostgreSQL et
MinIO sur un runner `medium`. Il contrôle le démarrage de Gunicorn, `/health/`,
un vrai média S3, la création d’un paquet de reprise et sa restauration dans
des cibles distinctes. Les bases, le bucket et les identifiants de ce scénario
n’existent que pendant le job et ne contiennent aucune donnée réelle.

## Le référentiel

`referentiel/trame-cycle1.yaml` est **une trame de travail, pas un référentiel
officiel**. Elle reprend les cinq domaines d'apprentissage et propose 57
formulations à la première personne. C'est le fichier à donner à l'école pour
qu'elle y mette ses propres progressions — c'est d'ailleurs le meilleur premier
échange à avoir avec elle.

Rechargement après modification :

```sh
python manage.py charger_referentiel referentiel/le-votre.yaml
```

Les réussites déjà saisies survivent tant que le champ `code` d'une compétence
ne change pas. Ajoutez `--desactiver-absents` pour retirer de la saisie les
compétences disparues du fichier, sans perdre les observations associées.

## Mettre en ligne pour le test

SQLite et les médias locaux conviennent au développement et à la démonstration
éphémère. Un environnement persistant exposé à une équipe utilise le profil
PostgreSQL + stockage objet privé décrit dans `DEPLOIEMENT.org`. Sa
configuration part de `.env.example` et son démarrage s'effectue avec :

```sh
./start-persistent.sh
```

Côté données personnelles : l'outil contient des prénoms d'enfants et
potentiellement des photos. Hébergement adapté, HTTPS, stockage privé,
sauvegardes coordonnées de PostgreSQL et des médias, et conversation avec la
direction sur ce qui est photographié restent indispensables. La formulation
retenue dans l'interface suggère de photographier les productions plutôt que
les visages.

## Sauvegarder et tester une restauration PostgreSQL

Le profil persistant dispose de scripts indépendants de l'hébergeur. Le
répertoire de sauvegarde doit être explicite, absolu et situé sur un stockage
durable distinct du système de fichiers éphémère de l'application :

```sh
export CARNET_BACKUP_DIR=/chemin/persistant/sauvegardes
scripts/sauvegarder-postgresql.sh
```

Chaque export au format personnalisé de PostgreSQL est accompagné d'une somme
SHA-256. La présence d'un fichier ne suffit cependant pas : une restauration
doit être testée périodiquement dans une base temporaire distincte :

```sh
export RESTORE_DATABASE_URL='postgresql://.../petits_pas_restauration'
export CARNET_AUTORISER_RESTAURATION=oui

scripts/restaurer-postgresql.sh \
  /chemin/persistant/sauvegardes/petits-pas-YYYYMMDDTHHMMSSZ.dump
scripts/verifier-restauration.sh
```

`restaurer-postgresql.sh` détruit le contenu existant de la base temporaire et
refuse de s'exécuter lorsque `RESTORE_DATABASE_URL` est textuellement identique
à `DATABASE_URL`. La base de restauration ne doit jamais être la base active.

Ces scripts PostgreSQL ne programment pas eux-mêmes les sauvegardes. Leur
planification, la rétention des exports et les essais réguliers de restauration
relèvent de la configuration de l'hébergeur.

Les médias peuvent également être exportés dans un format portable composé de
fichiers ordinaires et d’un manifeste SHA-256 :

```sh
export CARNET_BACKUP_DIR=/chemin/persistant/sauvegardes
scripts/sauvegarder-medias.sh

export CARNET_AUTORISER_RESTAURATION_MEDIAS=oui
scripts/restaurer-medias.sh \
  /chemin/persistant/sauvegardes/petits-pas-medias-YYYYMMDDTHHMMSSZ
```

La restauration refuse tout écrasement. Le contrat et les limites de cohérence
entre les sauvegardes SQL et médias sont détaillés dans `DEPLOIEMENT.org`.

Un paquet de reprise coordonné peut regrouper les deux sauvegardes :

```sh
export CARNET_BACKUP_DIR=/chemin/persistant/sauvegardes
scripts/sauvegarder-reprise.sh online
scripts/verifier-reprise.sh \
  /chemin/persistant/sauvegardes/petits-pas-reprise-YYYYMMDDTHHMMSSZ
```

Le mode `writes-suspended`, documenté dans `DEPLOIEMENT.org`, exige que
l’opérateur interrompe effectivement toutes les écritures.

Pour prouver qu’un paquet permet réellement une reprise, le profil local natif
peut effectuer un exercice complet dans une base PostgreSQL et un répertoire de
médias temporaires :

```sh
source scripts/activer-local-natif.sh
scripts/exercer-reprise-local.sh \
  "$PWD/backups/petits-pas-reprise-YYYYMMDDTHHMMSSZ"
```

Le script vérifie le paquet, restaure les deux composantes, contrôle les
migrations et l’existence de chaque média référencé par la base, puis supprime
ses cibles temporaires. La base active et ses médias ne sont jamais modifiés.
Pour conserver les cibles à des fins d’inspection, définir explicitement
`CARNET_CONSERVER_REPRISE_LOCALE=oui` avant l’exercice.

## Tester le profil persistant en local

### Variante native

Cette variante lance PostgreSQL comme processus utilisateur et conserve les
médias dans `.local-persistent/`. Le paquet `postgresql` doit être disponible
dans l'environnement.

Démarrage :

```sh
scripts/demarrer-local-natif.sh
source scripts/activer-local-natif.sh
python3 manage.py runserver
```

Arrêtez le serveur Django avec `Ctrl-C`, puis PostgreSQL avec :

```sh
scripts/arreter-local-natif.sh
```

Les données PostgreSQL et les médias sont conservés dans
`.local-persistent/` et seront retrouvés au prochain démarrage.

### Variante Compose

Cette variante lance PostgreSQL et MinIO afin de reproduire une architecture
avec stockage objet S3. Docker Compose ou Podman Compose est requis.

> **Note**
>
> Cette variante est préparée mais n’a pas encore été validée avec Podman
> rootless sous Guix System. La variante native constitue actuellement le
> chemin recommandé pour le développement local.

```sh
scripts/demarrer-local-compose.sh
source scripts/activer-local-compose.sh
python3 manage.py runserver
```

Arrêtez Django avec `Ctrl-C`, puis les services avec :

```sh
docker compose -f compose.local.yaml down
# ou :
podman compose -f compose.local.yaml down
```

Les volumes PostgreSQL et MinIO sont conservés. La commande suivante les
supprimerait définitivement et ne doit servir qu'à une réinitialisation
volontaire :

```sh
docker compose -f compose.local.yaml down --volumes
```

## Déployer le profil persistant

Le contrat indépendant de l’hébergeur, les variables d’environnement, la
commande de démarrage, les sondes et les responsabilités de sauvegarde sont
décrits dans [`DEPLOIEMENT.org`](DEPLOIEMENT.org). Un jeu de variables sans
secret réel est fourni dans [`.env.example`](.env.example).

L'environnement persistant réservé aux retours de l'équipe pédagogique est
décrit séparément dans
[`ATELIER-PEDAGOGIQUE.org`](ATELIER-PEDAGOGIQUE.org). Il n'accepte que des
données factices, affiche la version promue et ne réinitialise jamais ses
données lors d'un redéploiement.

## Générer les carnets PDF

La prévisualisation d'un carnet propose un téléchargement PDF produit à la
demande avec WeasyPrint. Le fichier reprend les filtres et le nombre de
colonnes choisis et n'est pas conservé sur le serveur. L'environnement Guix
inclut `weasyprint` et `poppler` ; hors Guix, les bibliothèques système requises
par WeasyPrint doivent être fournies par la plate-forme en complément de
`requirements.lock`. Les photos sont lues directement depuis le stockage
Django — local ou S3 privé — et ne dépendent pas d'une URL publique accessible
par le moteur PDF.

Le poids, le format, le nombre de pages et les images incorporées se contrôlent
avec :

```sh
scripts/analyser-pdf.sh chemin/vers/carnet.pdf
```

## Structure

```
carnet/          réglages, urls racine
suivi/           modèles, vues, templates, statiques
  management/commands/
    creer_ecole.py          crée une école et ses deux mots de passe
    charger_referentiel.py  charge/met à jour le YAML
    jeu_demo.py             données de démonstration
referentiel/     les fichiers YAML de compétences
scripts/         sauvegarde et vérification de restauration PostgreSQL
```

Six modèles : `Ecole`, `Classe`, `Eleve`, `Domaine`, `Competence`,
`Observation`. Tout est rattaché à l'école dès maintenant pour que
l'ouverture à plusieurs établissements ne demande pas de migration douloureuse.
