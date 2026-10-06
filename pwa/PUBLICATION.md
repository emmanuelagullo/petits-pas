# #PWA6a : publication à la demande sur GitLab Pages

Le job manuel **pwa-publication** publie le bundle du job **pwa-prototype**
réussi dans le **même pipeline** de `main` ou d’un tag numérique commun aux deux forges. La qualification doit aussi réussir. Il ne reconstruit pas l'application
et ne publie pas le bundle de `pwa-qualification`. Les données des essais ne
sont pas incluses. Depuis #PWA13, les versions maintenues visent la production sur le périmètre
décrit dans [PRODUCTION.md](PRODUCTION.md). Les bancs restent fictifs.

## Configuration initiale, une seule fois

La forge Inria utilise GitLab Community Edition. Le site Hugo conserve son
projet Pages ; la PWA utilise un petit projet distinct, dans son propre sous-chemin.
Ce choix ne dépend pas des déploiements Pages parallèles Premium/Ultimate.

1. Créer le projet **petits-pas/petits-pas-pwa**, sur la même forge, avec une
   branche `main`. La personne lançant `pwa-publication` doit pouvoir lancer
   les pipelines de ce projet. Les runners Inria `ci.inria.fr` / `small`
   doivent y être disponibles.
2. Dans ce projet, créer `.gitlab-ci.yml` avec le contenu de
   [`publication/gitlab-ci.yml`](publication/gitlab-ci.yml) :

   ```yaml
   include:
     - project: petits-pas/petits-pas
       ref: main
       file: pwa/publication/pages.yml
   ```

   Il n'y a ni clone du code applicatif ni second exemplaire à maintenir.
   Le push initial ne publie rien : seuls les pipelines déclenchés par le
   job de publication sont acceptés.
3. Après application de #PWA6b sur le dépôt principal, dans **Deploy → Pages**
   du projet PWA, désactiver **Use unique domain**. L'adresse attendue est
   `https://petits-pas.gitlabpages.inria.fr/petits-pas-pwa/`.
   Le même bundle fonctionne aussi à la racine d'un domaine dédié.
   Conserver ensuite cette adresse : un changement de domaine ou de chemin
   nécessite un transfert par ZIP. La portée du Service Worker est limitée
   à `/petits-pas-pwa/` ; le site Hugo `/petits-pas/` reste indépendant.
   Le stockage PWA est identifié par ce chemin, mais les deux sites partagent
   l'origine et le quota du navigateur : ce n'est pas une isolation de sécurité
   entre les projets. N'héberger sur cette origine que des contenus de confiance.
4. Pour un essai par simple lien, autoriser l'accès public au site Pages.
   Seuls les fichiers de l'application sont publiés ; chaque navigateur
   possède ensuite sa propre école locale. Cela ne constitue pas un partage
   des données entre appareils.

La création du projet et ses réglages demandent un compte GitLab autorisé ;
ils ne sont pas effectués par le patch du dépôt public. Aucune URL déjà
déployée n'est annoncée avant la première publication réussie.

## Publier une version

1. Après un push sur `main` ou du tag numérique, ouvrir son pipeline : **pwa-prototype** et
   **pwa-qualification** démarrent automatiquement.
2. Attendre la réussite des deux jobs, puis lancer **pwa-publication** dans ce même pipeline.
3. Suivre le pipeline lié du projet PWA et son job **pages**. Le job source
   attend le résultat du pipeline destinataire (`strategy: depend`).
4. Ouvrir l'adresse indiquée dans **Deploy → Pages** du projet PWA, ou dans
   l'environnement **prototype-pwa**. La transmettre aux personnes qui testent.

Les tags numériques doivent pointer sur le même commit sur GitHub et GitLab.
Le journal `CHANGELOG.org` doit contenir une rubrique correspondant au tag avant
sa construction. Sur `main`, les notes À venir sont embarquées au commit exact.
La version applicative (tag ou `dev.<commit>`) est affichée ; l’identité du
bundle reste accessible dans l’aide et conserve son rôle dans les caches.

Le job récupère le numéro exact du job réussi, pas « le dernier artefact de
main ». Il vérifie projet, commit et pipeline, refuse `testMode: true`,
contrôle chaque SHA-256 et le contenu complet du bundle, puis prépare `public/`.
Un rapport `publication-pwa.json`, également servi sous `publication.json`, relie l'adresse, la version, le commit, le
pipeline et les jobs de construction et qualification. Les manifestes et rapports sont servis sous `publication/`. Ce rapport est un artefact technique,
pas un fichier contenant les données d'une école.

Les API de pipeline et de téléchargement d'artefacts du projet public sont
utilisées sans authentification : aucun jeton personnel ni secret envoyé au
projet destinataire. Si leur visibilité est restreinte ultérieurement, le
téléchargement échouera et il faudra revoir cette configuration. Les autres
variables du pipeline source ne sont pas transférées.

Les artefacts de `pwa-prototype` expirent après 30 jours. S'ils ne sont plus
disponibles, relancer le prototype et, si nécessaire, la qualification avant de publier. Choisir normalement le pipeline
du `main` courant ; lancer un ancien pipeline est une demande explicite de
republier cette ancienne version, pas un retour automatique des données.

Les publications sont sérialisées par `resource_group: pwa-pages`. Un échec
avant la réussite du job Pages laisse la publication précédente en place.
Les deux jobs de test PWA sont automatiques et leurs échecs font échouer le
pipeline. Seule la publication reste facultative : une CI verte ne signifie
pas que le nouveau bundle a été publié.

## Mise à jour du projet Pages existant

Le fichier inclus `pages.yml` reste sur `main` du dépôt applicatif. Il prend
maintenant en charge les tags et télécharge aussi le validateur commun
`publication.py` au commit demandé. Aucun secret d’exploitation n’est ajouté.
Une ancienne construction dépourvue de manifeste n’est plus publiable :
reconstruire avec les scripts actuels. Pour revenir à un ancien code, intégrer
les outils de construction nécessaires dans un nouveau commit candidat ; ne
pas falsifier l’identité d’un artefact ancien. Conserver une copie du bundle
publié hors des artefacts CI si une reprise exacte est nécessaire.

## Après publication

Ouvrir le site dans Chromium récent. Attendre le premier chargement, créer
une école fictive et exporter une sauvegarde. Revenir à la même adresse après
mise à jour ; le bouton **Vérifier les mises à jour** permet de télécharger
la nouvelle version. Les cookies virtuels restent perdus à la fermeture.

Une école créée à `http://localhost:8000/` n'apparaît pas automatiquement sur
l'adresse Pages : la transférer par un ZIP. Ne pas effacer les données du
site pour actualiser l'application. La validation sur appareils d'école,
la mémoire totale et les coupures électriques restent à effectuer.

## Vérifications et limites de la livraison

Tests du préparateur :

```sh
python3 -m unittest discover -s scripts -p test_publication_pwa.py
```

Ils couvrent sélection du pipeline exact, pagination, job en échec ou mauvais
commit, mode test, altération, fichier inattendu, chemins/lien invalides et
URL Pages HTTPS à la racine ou dans un sous-chemin sûr. Le préparateur est aussi vérifié localement sur
le bundle de distribution de #PWA6, avec téléchargement HTTP et préparation
complète sur une API locale fictive. YAML et Hugo sont contrôlés.

La CI distante et le déploiement sur le nouveau projet ne sont pas exécutés
pour cette livraison : le projet doit d'abord être créé et configuré. Les
scénarios Django/HTMX de #PWA6 ne sont pas relancés, car le runtime et les
parcours applicatifs ne changent pas. Les références GitLab sont la
[documentation Pages](https://docs.gitlab.com/user/project/pages/) et
[l'API des artefacts](https://docs.gitlab.com/api/job_artifacts/).

## #PWA6b : adresse avec sous-chemin

Le runtime calcule son préfixe depuis l'emplacement des scripts : routes WSGI,
liens Django, médias, statiques, manifeste et ressources hors ligne suivent ce
préfixe. Le préparateur vérifie le bundle original sans réécriture ni changement
d'empreintes. Les caches et données internes sont propres au chemin de la PWA.

Le job `pwa-prototype` exécute les parcours à la racine puis sous
`/petits-pas-pwa/`, avec deux rapports distincts. Pour reproduire le second :

```sh
PWA_BASE_PATH=/petits-pas-pwa/ node scripts/verifier-pwa.cjs
```

Pour basculer sans données à conserver : appliquer le patch sur `main`, désactiver
le domaine unique dans le projet Pages, attendre `pwa-prototype`, puis lancer
`pwa-publication` dans le nouveau pipeline. Ouvrir l'adresse avec le `/` final.
Aucune modification du fichier CI du projet Pages n'est nécessaire.

Vérifications locales du 4 octobre 2026 : parcours Chromium à la racine et sous
`/petits-pas-pwa/`, y compris mises à jour, secours, photos et sauvegardes ;
la page Hugo fictive voisine reste hors du contrôle du Service Worker PWA.
Les 8 tests de publication, 18 tests du paquet autonome, la syntaxe, les YAML
et la construction Hugo passent. La suite Django complète et la qualification
550 photos ne sont pas relancées : les règles métier et le protocole de
persistance ne changent pas. La publication réelle reste à lancer sur GitLab.

## #PWA8a : échec du prototype et publication

L'ancienne configuration `allow_failure: true` rendait le bouton de publication
activable après un échec du prototype. Le projet Pages refusait déjà de publier
ce pipeline, en vérifiant son job exact. Le prototype est désormais automatique
avec `allow_failure: false` : sa dépendance CI devient bloquante en cas d'échec.
Le contrôle du projet destinataire reste une deuxième vérification indépendante.
Aucun changement du fichier CI du projet Pages n'est nécessaire.

## #SP6 : contrôles et récupération

#PWA11 ajoute `lazy_media.js` au bundle et à ses empreintes. Aucun changement
de projet Pages, de chemin, d'en-têtes COOP/COEP ou de format interne n'est
requis. Publier le bundle complet contrôlé par les mêmes jobs ; anciens ZIP et
manifestes sont repris. Depuis #PWA12, les transferts ZIP sont progressifs et limités à 256 Mio
décompressés, avec base et fichier individuel à 64 Mio. Voir TRANSFERTS-OPFS.md.
Le périmètre de production et les navigateurs qualifiés sont décrits dans
PRODUCTION.md ; la présence des API ne suffit pas à qualifier tous les moteurs. Voir `MEDIA-OPFS.md` et les mesures
`QUALIFICATION.md`.

La promotion vérifie les deux jobs du même commit, les empreintes du candidat,
les rapports racine/HTTPS et le démarrage du bundle final, puis le rapport
de qualification. Elle ne dépend pas de la réussite d’un déploiement d’école.
Les essais terrain restent non bloquants.

Mettre à jour le logiciel et restaurer une école sont distincts. Avant toute
mise à jour, conserver un ZIP hors appareil. Un ancien logiciel peut ne pas
lire des données migrées ; le republier ne restaure pas l’école. Vérifier un
ZIP dans une copie indépendante avant son adoption confirmée. La récupération
peut contenir un état antérieur aux dernières saisies. Ne pas effacer les
données du navigateur pour actualiser les ressources.

## #PWA13 : promotion d’une version maintenue

Avant promotion, appliquer les contrôles de dépendances de PRODUCTION.md et
attendre les rapports du runtime courant, y compris volume et interruptions.
Le nom historique `pwa-prototype` et l’environnement `prototype-pwa` restent
compatibles avec le projet Pages existant ; aucun changement de ses réglages
n’est requis. Une publication ancienne garde son statut et son aide. Pour
annoncer la nouvelle version aux utilisateurs, publier le nouveau bundle
contrôlé puis vérifier sa version affichée. Les retours terrain restent non bloquants.
