# Contribuer à Petits Pas

Merci de l'intérêt porté à Petits Pas. Le projet accueille les corrections,
les propositions fonctionnelles, les retours d'usage et les contributions au
code ou à la documentation.

## Diagnostiquer un téléchargement du socle en CI

En cas de HTTP 502 sur le wheel, lancer manuellement `diagnostic-wheel` dans
le pipeline Inria concerné. Ce job utilise la même image Python et le même
profil de runners que les tests, sans installation de dépendances. Il relève
les DNS, la présence de variables proxy (sans leurs valeurs), les hôtes des
redirections et quelques en-têtes HTTP. Il compare l’URL épinglée à une requête
distincte avec `no-cache` et vérifie l’empreinte du wheel reçu. Les sondes PyPI
et GitHub servent de témoins. Un échec DNS local peut coexister avec un accès
HTTP fonctionnel lorsque le proxy résout lui-même les noms.

Le job finit en échec si l’URL exacte ne fournit pas le wheel attendu, même si
la requête distincte fonctionne. Il est facultatif et ne participe pas à la
qualification ; les tests, constructions et contrôles de publication restent
obligatoires. Une différence entre les deux requêtes suggère un effet de cache
ou de routage, sans suffire à identifier son responsable. Ne pas adopter la
variante de diagnostic comme URL de dépendance sans analyser les résultats.

Le script s’exécute aussi depuis la racine :
`python3 scripts/diagnostiquer-wheel.py`. Il ne conserve aucun téléchargement.

## Licence des contributions

Sauf mention explicite acceptée avant la contribution, toute contribution au
code est proposée sous la licence `AGPL-3.0-or-later` et toute contribution à
la documentation publique sous la licence `CC-BY-SA-4.0`.

En soumettant une contribution, son auteur confirme qu'il a le droit de la
publier sous la licence correspondante. Aucun transfert de copyright n'est
demandé.

Les photographies, productions d'enfants, données d'établissement ou autres
données personnelles ne doivent jamais être ajoutées au dépôt. Les exemples,
tests, démonstrations et captures doivent employer exclusivement des données
fictives.

## Vérifications

Avant de proposer une modification, exécuter lorsque cela s'applique :

```sh
python3 manage.py collectstatic --noinput
python3 manage.py test --settings=carnet.settings_tests --durations 30 --timing
python3 manage.py makemigrations --check --dry-run
bash -n start-atelier.sh start-persistent.sh start-render.sh scripts/*.sh
hugo --source site --minify
git diff --check
```

`carnet.settings_tests` accélère uniquement le hachage des mots de passe
fictifs. Il doit être choisi explicitement : ne pas l'utiliser pour lancer
le service, préparer une école ou construire une distribution. Les tests
d'authentification ordinaire et le scénario d'export complet d'école gardent
le hachage Django par défaut ; les sous-processus d'export utilisent
`carnet.settings`. Pour comparer avec les paramètres habituels, omettre
`--settings=carnet.settings_tests`.

`--durations 30` affiche les trente tests les plus lents ; `--timing`
distingue notamment la préparation des bases de leur utilisation. Les fixtures
de classe ne sont pas attribuées à chaque durée individuelle. Comparer les
durées à environnement équivalent.

Les tests de scripts ne sont pas découverts par `manage.py test`. La CI
exécute leurs commandes dédiées : notamment
`python3 -m unittest discover -s scripts -p test_version_application.py`
dans les jobs Django, et
`node --test scripts/test_transport_pwa.cjs scripts/test_recherche_referentiel.cjs scripts/test_classement_competence.cjs`
dans le job PWA, qui dispose déjà de Node.

Les vérifications GitLab marquées `interruptible` peuvent être annulées
lorsqu'un nouveau commit arrive sur la même branche. Les déploiements de
vérification et les publications ne le sont pas. Sur GitHub, une nouvelle
construction de la même branche remplace la précédente ; les constructions
de tags ne sont pas annulées automatiquement.


Pour une évolution du socle, utiliser aussi QUALIFICATION.md de pas-communs :
la recette vérifie code et ressources importés contre le wheel et les deux
adoptions épinglées. Elle ne fait aucune installation. Sous Guix, les outils
peuvent venir de l'environnement et le candidat être extrait dans un dossier
privé placé dans PYTHONPATH. Les versions Python des profils restent distinctes.

Pour la consommation TOTP : `python3 scripts/qualifier-totp.py` crée une vraie
SQLite temporaire et exerce deux connexions concurrentes, la réinitialisation
pendant calcul et le verrouillage. Le job Django GitLab le lance dans les deux
profils de dépendances ; les tests ordinaires exercent aussi PostgreSQL.

## Troisième hébergement : Forge Éducation

Inria reste la référence ; GitHub et la Forge Éducation reçoivent les mêmes
commits et tags. Le dépôt applicatif Éducation est
<https://forge.apps.education.fr/petits-pas/petits-pas> et son auxiliaire Pages
est <https://forge.apps.education.fr/petits-pas/petits-pas-pwa>.

Dans les deux projets, activer **Paramètres → CI/CD → Runners → Activer les
runners d'instance pour ce projet** (et autoriser leur utilisation au niveau
du groupe si nécessaire). Le runner d'instance #385 utilise Kubernetes sous
Linux amd64, accepte les jobs sans étiquette et impose au plus deux heures
par job. La CI sélectionne ce profil sur `forge.apps.education.fr` ; Inria
conserve ses étiquettes `ci.inria.fr` et ses tailles `small` / `medium`.
Aucune variable CI de sélection de runner n'est à créer.

Pour initialiser le miroir vide, depuis le dépôt applicatif local complet,
après application du patch et récupération du main courant :

```sh
git remote add education https://forge.apps.education.fr/petits-pas/petits-pas.git
git push education main
```

Dans un clone de l'auxiliaire Inria `petits-pas-pwa`, ajouter de même le remote
`https://forge.apps.education.fr/petits-pas/petits-pas-pwa.git` et pousser `main`.
À défaut de clone existant, créer sa branche `main` avec uniquement le fichier
`.gitlab-ci.yml` fourni dans `pwa/publication/gitlab-ci.yml` de l'application.
Ne pas copier le code de l'application dans cet auxiliaire.

Vérifier que la branche par défaut des deux projets est `main`, que les deux
projets et les artefacts CI nécessaires à la publication sont publics, puis
suivre `pwa/PUBLICATION.md` pour les réglages Pages et la première publication
d’une branche ou d’un nouveau tag qualifié sur Inria. Le pipeline initial de
l'auxiliaire seul est volontairement filtré. Utiliser l'adresse réellement
indiquée par Pages ; aucune adresse Éducation n'est présumée ici. Cette adresse
possède son propre stockage navigateur : transférer une école par ZIP si besoin.

Pour les mises à jour, pousser `main` sur chaque remote. Pour une nouvelle
version qualifiée, pousser son tag identique sur les trois hébergements. Les
anciens tags peuvent être archivés avec `git push -o ci.skip education --tags`
si cette option est autorisée par l'instance ; cela évite de reconstruire et
republier automatiquement chaque ancienne version lors de l'initialisation.
Ne pas utiliser `git push --mirror` sur un dépôt de travail ordinaire.

Les dépendances épinglées gardent leurs sources actuelles : wheel sur GitHub,
thème Hugo sur Inria, images de conteneurs et runtime PWA externes. Les téléchargements
restent sur GitHub ; les liens PWA du site Éducation visent sa propre publication. Le miroir Éducation
n'est donc pas encore un hébergement indépendant de ces services.
La compatibilité effective des images de publication, ressources mémoire et
durées devra être vérifiée au premier pipeline Kubernetes ; une
configuration valide ne vaut pas qualification du runner distant.

### Publication légère sur Éducation

La CI complète Inria est définie dans `.gitlab/ci/validation.yml` ;
`.gitlab-ci.yml` choisit le profil selon la forge. Tout push de branche ou de
tag sur Éducation lance le profil léger. Pour une reprise manuelle, créer un
pipeline en sélectionnant la branche ou le tag dans **Build → Pipelines → New
pipeline**, ou relancer ses jobs en échec. Ne pas déplacer un tag déjà publié.
Le site Hugo est publié sur branche ou tag numérique ; la PWA habituelle est
publiée sur branche ou tag stable sans suffixe. Les préversions ne la remplacent
pas.

Ordre habituel :

1. Pousser `main` et le tag de version sur Inria et GitHub.
2. Attendre la réussite complète du pipeline Inria du tag et la publication
   de la release GitHub avec ses binaires.
3. Pousser `main`, puis ce seul tag, sur Éducation :

   ```sh
   git push education main
   git push education 0.12.0
   ```

Éducation sélectionne le plus récent pipeline Inria **réussi de la référence et
du SHA exacts**, vérifie l'identité du tag GitHub (ou la présence du commit
GitHub sans tag), importe les captures et l'école
fictive du job `captures-demonstration`, et actualise le catalogue GitHub.
Sur tag, la release attendue doit y figurer. Sans tag, le catalogue est
actualisé avec les releases existantes, sans exiger de nouvelle release.
Une erreur réseau, ou une release attendue absente sur tag, fait échouer la
préparation sans publier un catalogue périmé.
Hugo reconstruit le site pour son URL Pages et le vérificateur de liens contrôle
cette sortie. Les liens d'ouverture de la PWA suivent le paramètre Hugo
`pwaURL`, fixé à `/petits-pas-pwa/` sur Éducation (désactiver les domaines uniques
des projets Pages pour cette configuration).

L'auxiliaire PWA reçoit ensuite la référence et le SHA Éducation, retrouve le pipeline
Inria qualifié correspondant, puis publie le **bundle existant**, sans le
reconstruire. Le préparateur existant vérifie toujours jobs, candidat,
qualification, rapports et empreintes. `publication.json` indique maintenant
`source_api` afin de distinguer la provenance Inria de l'URL publiée Éducation.
Aucun secret ni jeton interforge n'est nécessaire : les API et artefacts source
doivent rester publics.

Les sources sont les artefacts CI Inria, pas une copie de l'URL PWA courante.
Un artefact expiré, inaccessible ou altéré bloque la publication, sans retour
silencieux à une autre version. Les captures expirent après une semaine, les
artefacts PWA après trente jours : pour une publication tardive, relancer les
jobs Inria du tag exact, attendre la réussite de son pipeline, puis relancer
Éducation. Un push trop précoce sur Éducation reste en attente manuelle, selon la procédure
ci-dessous, jusqu'à réussite Inria et, sur tag, publication GitHub. Les sites Hugo et PWA sont deux
publications successives : un échec PWA peut survenir après la mise à jour Hugo ;
relancer alors `pwa-publication`.

Le fichier `.gitlab-ci.yml` de l'auxiliaire `petits-pas-pwa` ne change pas :
il continue d'inclure `pwa/publication/pages.yml` depuis `main` de la même forge.
Pousser le nouveau `main` sur Éducation avant le premier nouveau tag est donc
nécessaire. Les anciens tags n'incluent pas ce profil : ne pas les pousser sans
`ci.skip` pour initialiser l'archive du miroir.

Pour publier ponctuellement sans créer de version, pousser la même branche sur
Inria et GitHub, attendre son pipeline Inria réussi avec les artefacts requis,
puis pousser cette branche sur Éducation :

```sh
git push education main
```

Le pipeline est automatique et met à jour Pages ainsi que la PWA du commit
validé. Il ne prend jamais « le dernier main » à la place du SHA poussé.
Si la branche Inria a avancé depuis, son pipeline réussi du SHA exact reste
sélectionné. Si les règles Inria n'ont pas généré les captures pour ce commit,
lancer un pipeline manuel Inria sur la référence pour produire les artefacts,
puis reprendre la publication Éducation. Cette possibilité de pousser sans tag
est un choix d'usage, pas une restriction de la CI.

### Attente Inria sans échec de publication

Chaque push Éducation lance d'abord `disponibilite-inria`. S'il existe une
validation Inria réussie du SHA et de la référence exacts, le job `publication`
lance automatiquement les quatre tâches dans un pipeline enfant : import,
construction Hugo, publication Pages, puis publication PWA.

Si le commit ou le tag n'a pas encore été poussé, si aucun pipeline n'existe,
ou s'il est encore en cours/en attente, le contrôle termine normalement. Le
pipeline enfant affiche `source-inria` comme **manuel, non lancé**, et les
publications ne démarrent pas. GitLab signale une action manuelle attendue
(`blocked`), sans échec ni avertissement `allow_failure`. Le déclencheur utilise
`strategy: mirror` pour refléter cet état dans le parent (GitLab >= 18.2). Aucun runner n'attend
en boucle et aucune publication précédente n'est remplacée.

Après réussite Inria (et présence de la release GitHub pour un tag), ouvrir le
pipeline enfant depuis `publication`, puis lancer **source-inria** avec le
bouton de lancement et confirmer. Aucun nouveau push n'est nécessaire. L'import
et la publication refont leurs contrôles stricts ; lancer trop tôt peut donc
encore échouer. Le contrôle ne s'actualise pas automatiquement après sa fin.

Un pipeline Inria échoué/annulé, un SHA différent, une API inaccessible ou un
artefact expiré/altéré restent de véritables erreurs. Le job manuel utilise
`allow_failure: false` : son échec après lancement fait échouer la chaîne, au
lieu de transformer toutes les erreurs de publication en avertissements.

### Téléchargement des dépendances en CI

Les profils GitLab et de publication PWA fixent `PIP_RETRIES=10` et
`PIP_TIMEOUT=60` pour mieux supporter les réponses HTTP 502 intermittentes.
Les reprises sont celles du client réseau pip ; aucun test échoué n’est relancé
automatiquement. Les versions et empreintes de `requirements-communs.txt`
restent verrouillées. Si le serveur reste inaccessible après les reprises,
le job échoue normalement : ne pas désactiver HTTPS ni le contrôle du SHA-256.
