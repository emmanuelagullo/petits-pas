# #PWA1 à #PWA6 : prototype navigateur

Expérience réservée aux **données fictives**. Aucun profil serveur ou programme
autonome n'est remplacé. Le prototype propose l'import/export commun,
l'impression PDF et les mises à jour avec récupération. #PWA6 remplace les
ZIP de travail par une persistance incrémentale ; appareils d'école et
production restent à qualifier.

## Essayer et mettre à jour le premier prototype

Python 3 avec pip et Internet sont nécessaires à la construction :

```sh
python3 scripts/construire-pwa.py
python3 -m http.server 8000 --directory dist/pwa
```

Ouvrir **http://localhost:8000/** dans Chromium récent, dans un profil dédié.
Le site doit occuper la racine d'une origine dédiée. Hors localhost, HTTPS est
obligatoire. Le dossier `dist/pwa` est un site statique ; aucun serveur Python
n'est nécessaire à l'utilisation. Après le premier téléchargement, les
ressources et le runtime sont utilisables hors ligne.

Pour reprendre une installation #PWA1/#PWA2, conserver **la même adresse et le
même port**, reconstruire, puis fermer tous les onglets de cette installation
et la rouvrir. Le nouveau Service Worker reprend les instantanés précédents,
même dépourvus de manifeste. Si l'ancienne page reste affichée après la prise
en charge par le nouveau Service Worker, la recharger. Exporter auparavant un
ZIP depuis la version actuelle. Ne jamais effacer les données du site pour
mettre à jour une école à conserver.

L'école appartient au profil de navigateur et à l'origine. Se reconnecter
après rechargement. Le stockage local n'est pas chiffré ; un ZIP comprend toutes
les données de l'école et la clé. Le bouton de protection du stockage ne
remplace pas une sauvegarde externe.

## Sauvegardes communes (#PWA3)

La page existante **Gérer l'école → Sauvegardes locales** reste réservée à la
direction. `suivi.paquet_local` fournit l'export et la vérification communs :
SQLite cohérent par `backup()`, clé, médias, manifeste SHA-256, chemins sûrs,
contrôle d'intégrité et de relations SQLite. La PWA ajoute des limites et la
vérification des migrations connues, sans remplacer ce validateur.

À l'import : vérifier le ZIP, consulter les détails, annuler ou confirmer.
La confirmation ferme les connexions Django, active le paquet **en mémoire**,
applique les migrations connues, efface les cookies virtuels et prépare un
nouvel instantané. Le Worker attend ensuite l'écriture OPFS et l'activation du
pointeur IndexedDB avant d'envoyer la redirection vers la connexion. Une erreur
bloque le runtime ; le dernier OPFS confirmé reste la référence à la réouverture.
Le remplacement en mémoire n'est pas une activation durable par renommage.

L'instantané avant remplacement reste conservé à travers les requêtes
suivantes. Il est remplacé au prochain import ou changement de version réussi.
**Exporter l'état de récupération** produit lui aussi un ZIP autonome. En
fonctionnement normal, ce bouton vérifie le droit de direction. Après échec du
démarrage, il reste accessible sans authentification, dans un Worker séparé qui
ne migre pas et n'écrit rien : c'est un accès de secours pour le propriétaire du
profil, analogue à la lecture des fichiers du paquet bureau. Ne pas utiliser
un profil partagé avec des personnes non autorisées. Les autorisations Django
ne chiffrent pas les données OPFS et ne protègent pas contre un accès direct au
profil ou du JavaScript exécuté sur la même origine.

Limites du prototype : envoi HTTP/multipart ≤ 70 Mio, contenu ZIP décompressé
≤ 64 Mio, ≤ 5 000 entrées. L'état de travail est limité à 64 Mio avant
compression, manifeste ZIP public compris. Les médias restent
aussi en mémoire ; cette borne technique ne qualifie pas la RAM d'une tablette.
La coque avertit dès 52 Mio. L'espace OPFS réel comprend aussi l'état précédent,
le secours et les ressources, et peut dépasser 64 Mio. Un quota navigateur plus
faible reste possible. Un import dépassant la persistance bloque le runtime,
et l'ancien état reste actif. Ces limites ne sont pas des quotas de production.

## Stockage incrémental (#PWA6)

SQLite reste **natif Pyodide dans MEMFS**, avec `journal_mode=DELETE` : ce n'est
pas SQLite WASM/OPFS utilisé directement par Django. Après chaque requête, une
copie SQLite cohérente par `backup()` est comparée par SHA-256. La méthode HTTP
ne décide pas si une sauvegarde est nécessaire. La session PWA conserve sa durée
maximale de 12 heures mais ne prolonge plus son échéance à chaque lecture ; les
cookies virtuels sont toujours perdus à la fermeture du Worker.

Les écritures/suppressions des médias passent par `pwa.media_storage`, propre
à ce profil, qui retient les noms modifiés. Leur empreinte est recalculée ; les
médias inchangés ne sont ni relus ni recopiés à chaque consultation. Un inventaire
complet est effectué au démarrage, après restauration et pour le protocole
Python des tests. Les futurs traitements qui écriraient directement dans MEMFS
hors du stockage Django devront aussi invalider cet inventaire.

Les blobs et le manifeste sont immuables dans OPFS. Les blobs nouveaux sont
écrits, `flush()` puis fermés ; le manifeste fait ensuite de même. Une transaction
IndexedDB de durabilité `strict` active sa référence et son SHA-256. **Une seule
activation réunit la base, la clé et tous les médias.** Sans différence de contenu,
aucun fichier OPFS ni pointeur actif n'est réécrit. La base entière est encore
recopiée lors d'une modification SQL ; elle n'est pas persistée page par page.
Le transport HTTP local utilise des buffers binaires transférables, sans
base64 ni corps HTTP dans le JSON des métadonnées.

La réouverture vérifie manifeste et empreinte de chaque blob avant toute
migration. Elle refuse un fichier absent/altéré sans créer une école vide.
Actif, précédent et secours peuvent partager des blobs ; le nettoyage garde
l'union de leurs références et supprime les orphelins après activation réussie.
Un nettoyage raté n'annule pas une saisie déjà enregistrée.

Les ZIP #PWA1–#PWA5 restent lisibles. Leur conversion en format interne 2 est
activée après migration et le ZIP d'avant version est conservé en secours.
Exporter avant la mise à jour : un ancien exécutable ne lit pas ce nouveau
format interne. Les sauvegardes exportées restent des ZIP du paquet autonome,
produits à la demande par `suivi.paquet_local`, sans modification du format public.

## Impression et mises à jour (#PWA4)

Les routes `.pdf` du carnet et de la grille réutilisent les contextes et droits
métier communs, avec leurs URLs de photos autorisées. Elles servent une page
HTML imprimable. **Préparer l'impression / PDF** puis **Imprimer / enregistrer
en PDF** ouvre le dialogue du navigateur ; choisir l'option PDF si disponible.
Ce n'est pas un téléchargement PDF calculé par Django/WeasyPrint.

La préparation pour plusieurs enfants garde les choix communs et réunit les
fragments du carnet dans un document à imprimer. Elle ne fabrique pas un ZIP
de PDF individuels. Le fragment du carnet est partagé avec le rendu serveur
et autonome ; WeasyPrint reste inchangé dans ces deux profils.

**Vérifier les mises à jour** télécharge une nouvelle version en attente.
**Appliquer la mise à jour** termine les requêtes en file, enregistre un état,
arrête le Worker et active le Service Worker suivant. Une version en attente
peut également s'activer après fermeture de tous les clients. Le nouveau
runtime vérifie les migrations, migre sa copie en mémoire, puis persiste ;
il conserve l'état avant version. Une base comportant des migrations inconnues
est refusée avant migration, sans créer une école vide. Exporter le secours et
le restaurer dans une version compatible ; aucun retour automatique vers un
ancien exécutable ou une ancienne base n'est imposé.

## Vérification et artefact CI

Node.js, Chromium Playwright, Python et `pdftotext` (poppler-utils) sont nécessaires :

```sh
npm install --prefix pwa --ignore-scripts
node pwa/node_modules/playwright/cli.js install --with-deps chromium
python3 scripts/construire-pwa.py --test
node scripts/verifier-pwa.cjs
python3 -m unittest discover -s scripts -p test_paquet_local.py
```

`PWA_CHROMIUM=/chemin/chromium` choisit un navigateur installé.
`PWA_OLD_BUNDLE=/chemin/ancien-bundle-test` ajoute le passage réel depuis
#PWA1–#PWA5. Le script démarre son serveur statique et utilise un contexte
navigateur temporaire, avec école, élève et image entièrement fictifs.
Résultats : `dist/pwa/resultats-tests.json`. Les caches `--runtime DOSSIER`
et `--wheels DOSSIER` évitent les téléchargements pendant la construction.

**Ne jamais publier un bundle `--test`** : il expose l'exécution Python des
essais. Reconstruire sans cette option après les tests. Le job manuel GitLab
**pwa-prototype** effectue les essais puis reconstruit sans protocole de test.
Il livre `dist/pwa/` et `resultats-pwa.json`, sans école ni secret local.
Il ne publie pas le site automatiquement et n'interrompt pas Hugo/Django.

## Déploiement statique pilote

Servir le contenu de `dist/pwa` à la racine d'une **origine dédiée stable**, en
HTTPS, avec types MIME corrects (`.js/.mjs` JavaScript, `.wasm`
`application/wasm`). Pas de proxy `/app/` vers Django : le Service Worker
intercepte ces routes. L'entrée utilisateur est toujours `/`.

Publier un bundle complet d'un seul coup (répertoire versionné puis changement
de la racine statique), avec `Cache-Control: no-cache` pour `sw.js` et
`config.json`. Ne pas mélanger les fichiers de deux constructions. Le cache
vérifie les SHA-256 du bundle à l'installation ; une installation incomplète
n'active pas la nouvelle version. Conserver l'ancien dossier publié pour
pouvoir réparer une publication, sans imposer un retour de données.

Le déploiement n'a pas besoin de COOP/COEP dans cette architecture. S3, SMTP,
pywebview, serveur WSGI réseau et moteur PDF ne sont pas embarqués. Le site
Hugo du projet, servi sous un sous-chemin, n'est pas la destination de ce bundle.
Aucune URL pilote publique ni machine d'école n'est provisionnée par ce patch.

## Qualification restante

Les essais sont réalisés sur Chromium 138 headless/Linux et Playwright 1.62.1.
Ils couvrent l'aller-retour ZIP natif, la confirmation/annulation, la photo,
les droits testés, l'impression Chromium, les erreurs injectées, l'intégrité,
la relance hors ligne, les mises à jour et le secours après refus au démarrage.
Ce ne sont pas des mesures sur tablette ou réseau d'école.

#PWA5 qualifie un scénario de volume, un quota Chromium contraint et des
arrêts SIGKILL ; voir [QUALIFICATION.md](QUALIFICATION.md). Il reste à qualifier
Safari/Firefox/Android, l'installation PWA, l'impression interactive réelle,
les grands carnets sur appareils d'école, un disque physiquement plein et la
coupure électrique. #PWA6 sauvegarde les fichiers modifiés après chaque
réponse et active leur manifeste commun, sans ZIP intermédiaire.
Web Lock et file exclusive du Worker sont indispensables ; seuls eux
justifient `DJANGO_ALLOW_ASYNC_UNSAFE` dans ce profil Pyodide.

Les versions Pyodide/Django/wheels et la maintenance de sécurité doivent être
requalifiées avant production. Synchronisation, sauvegarde automatique hors
appareil, chiffrement et travail concurrent restent hors périmètre. Ne pas
considérer #PWA6 comme une validation de production sur données réelles.

## Vérifications de livraison #PWA3/#PWA4

Le 3 octobre 2026 : 22 scénarios navigateur passent, dont une vraie migration
SQL ajoutée à un bundle d'essai lors de la mise à jour. Le passage réel du
bundle #PWA1/#PWA2 au nouveau runtime a aussi été vérifié avec l'option
`PWA_OLD_BUNDLE`. Les 18 tests du paquet autonome et 27 tests Django ciblés
(installation, sauvegardes, carnets et grilles) passent ; aucune migration de
modèle n'est créée. Hugo, syntaxes et YAML CI ont été vérifiés.

La suite Django complète et le job GitLab sur runner ne sont pas exécutés dans
cette livraison. Le job manuel est à lancer après application du patch.

## #PWA5/#PWA6 : volumes et interruptions

```sh
python3 scripts/construire-pwa.py --test
node scripts/qualifier-pwa.cjs
```

Ce banc Linux crée un profil Chromium persistant temporaire. Il ne termine
que le groupe de processus Chromium qu'il a lui-même lancé. Le serveur reste
actif pour préserver la même origine lors des reprises. École de 120 élèves,
six classes, jusqu’à 550 JPEG synthétiques distincts de 107 Kio : toutes les
données sont fictives.
Résultats : `dist/qualification-pwa.json`, hors du bundle distribuable.
Le job manuel **pwa-qualification** publie ce rapport, y compris en cas d'échec,
et ne publie pas le bundle de test. `PWA_CHROMIUM` sélectionne un exécutable.

Le protocole `test-metrics` et les pauses avant/après activation ne sont
accessibles qu'avec `--test`. L'inventaire de l'état et la persistance sont
mesurés, avec le nombre d'octets écrits par lecture (attendu : zéro). Le tas WASM est une capacité allouée, pas une mesure de toute
la RAM ; la PSS Linux est indiquée seulement si `/proc` autorise sa lecture.
Les mesures de lecture passent par le pont WSGI/Worker sans inclure le rendu
visuel ni tous les échanges du Service Worker.

Les essais imposent une erreur réelle de quota via Chromium et un SIGKILL
avant/après activation, puis vérifient SQLite et le SHA-256 de chaque photo.
Ils exportent et réimportent aussi un ZIP de 550 photos par le parcours commun.
Après restauration et confirmation OPFS/IndexedDB, la copie du paquet remplacé
en mémoire est libérée ; le secours OPFS reste conservé. Les résultats et
limites de la livraison sont consignés dans `QUALIFICATION.md`.
