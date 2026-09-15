# Carnet de suivi des apprentissages — V0

Un carnet numérique de suivi pour le cycle 1, dans l'esprit d'Iticarnet, qui
ferme fin mai 2027. Cette V0 vise **une seule école, un seul trimestre de
test** : elle est faite pour être mise entre les mains d'une enseignante vite,
et pour être jetée ou réécrite après.

Django 5/6 + HTMX + SQLite. Aucune dépendance distante au moment de l'affichage
(htmx est embarqué), parce que le wifi des écoles n'est pas fiable.

## Ce qu'elle fait

- Trois écrans de travail : la classe, un enfant, une compétence.
- **Saisie par enfant** : la liste complète du référentiel, filtrable par
  section. Un appui = réussi, deux = en cours, trois = effacé.
- **Saisie éclair** : une compétence observée, toute la classe sur un écran.
- **Trace** : un commentaire et une photo par réussite.
- **Carnet imprimable** : une page par enfant, en serif, pensée pour être
  donnée aux parents. `Ctrl+P` produit un PDF correct sans bibliothèque.
- Deux mots de passe pour l'école, enseignant et direction, comme Iticarnet.
- Import d'une liste d'élèves par copier-coller.

## Ce qu'elle ne fait pas

Volontairement, pour tenir dans une V0 :

- **Une seule observation par couple (enfant, compétence).** Pas d'historique :
  si vous repassez une compétence de « réussi » à « en cours », la date
  précédente est perdue. C'est le premier point à valider avec l'enseignante —
  si elle veut plusieurs traces datées par compétence, le modèle change.
- Pas d'inscription en ligne : les écoles se créent en ligne de commande.
- Pas de comptes individuels : le mot de passe est partagé par l'équipe. On ne
  sait donc pas qui a saisi quoi.
- Pas d'envoi de carnet aux parents, pas d'espace parent.
- Photos stockées telles quelles, sans redimensionnement.
- Pas de synthèse de fin de GS, pas d'export ONDE.

## Démarrer

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py creer_ecole "École maternelle des Tilleuls" --commune "Angoulême"
# notez les deux mots de passe affichés, ils ne sont pas stockés en clair

python manage.py charger_referentiel referentiel/trame-cycle1.yaml
python manage.py runserver
```

Pour voir l'outil rempli avant de le montrer à quelqu'un :

```sh
python manage.py jeu_demo    # une classe de 16 enfants et ~300 observations
```

Les tests couvrent l'accès, le cycle de bascule, l'isolation entre écoles,
l'import et le rechargement du référentiel :

```sh
python manage.py test suivi
```

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

SQLite tient très largement la charge d'une école. Le minimum avant d'ouvrir
l'accès depuis l'extérieur :

```sh
export CARNET_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
export CARNET_DEBUG=0
export CARNET_HOSTS="carnet.mon-domaine.fr"
export CARNET_CSRF_ORIGINS="https://carnet.mon-domaine.fr"
python manage.py collectstatic
gunicorn carnet.wsgi   # derrière nginx/caddy, en HTTPS
```

En `CARNET_DEBUG=0`, Django ne sert plus `media/` : confiez-le au serveur web.

Côté données personnelles : l'outil contient des prénoms d'enfants et
potentiellement des photos. Hébergement dans l'UE, HTTPS, sauvegarde du fichier
`carnet.sqlite3` et du dossier `media/`, et une conversation avec la direction
sur ce qui est photographié. La formulation retenue dans l'interface suggère de
photographier les productions plutôt que les visages.

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
