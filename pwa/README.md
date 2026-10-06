# Application navigateur — #PWA13

Petits Pas fonctionne localement dans le navigateur, y compris hors ligne.
La version maintenue a vocation à la production sur le périmètre déclaré dans
[PRODUCTION.md](PRODUCTION.md) : garanties, navigateurs, entretien et limites.
Les démonstrations et bancs utilisent exclusivement des données fictives.
Les profils serveur et programme autonome restent disponibles.

## Construire et mettre à jour

Python 3 avec pip et Internet sont nécessaires à la construction :

```sh
python3 scripts/construire-pwa.py
python3 -m http.server 8000 --directory dist/pwa
```

Ouvrir **http://localhost:8000/** dans Chromium récent, dans un profil dédié.
Le site peut occuper la racine ou un sous-chemin terminé par `/`. Hors localhost, HTTPS est
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
ne migre pas et ne modifie pas l'état confirmé : c'est un accès de secours pour le propriétaire du
profil, analogue à la lecture des fichiers du paquet bureau. Ne pas utiliser
un profil partagé avec des personnes non autorisées. Les autorisations Django
ne chiffrent pas les données OPFS et ne protègent pas contre un accès direct au
profil ou du JavaScript exécuté sur la même origine.

Limites : contenu décompressé et état de travail ≤ 256 Mio, manifeste compris,
≤ 5 000 entrées ; base et fichier individuel ≤ 64 Mio. Le multipart est reçu
par blocs sur OPFS (≤ 270 Mio avec son enveloppe) ; les autres requêtes restent
limitées à 70 Mio. La coque avertit dès 205 Mio. SQLite, sa copie cohérente et
les images effectivement traitées utilisent encore la mémoire. Le ZIP complet
et tous les médias extraits ne sont plus matérialisés ensemble dans Python ou JS.
Voir [TRANSFERTS-OPFS.md](TRANSFERTS-OPFS.md) pour les copies résiduelles,
la reprise et l'espace disque temporaire. Ces bornes ne qualifient pas la RAM
d'une tablette ; le quota navigateur peut être inférieur. Une erreur de
persistance bloque le runtime et l'ancien état reste actif après réouverture.

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
essais. Reconstruire sans cette option après les tests. Le job automatique GitLab
**pwa-prototype** effectue les essais puis reconstruit sans protocole de test.
Il livre `dist/pwa/` et `resultats-pwa.json`, sans école ni secret local.
Il ne publie pas le site automatiquement et n'interrompt pas Hugo/Django.

Pour publier ensuite par un clic, le job **pwa-publication** de `main`
déclenche le projet Pages dédié et réutilise l'artefact exact de ce pipeline.
Voir [PUBLICATION.md](PUBLICATION.md) pour sa configuration initiale, le sous-chemin
et les étapes. Le site Hugo conserve sa publication actuelle.

## Déploiement statique

Servir le contenu de `dist/pwa` à une **adresse stable**, à la racine ou sous
`/petits-pas-pwa/`, en
HTTPS, avec types MIME corrects (`.js/.mjs` JavaScript, `.wasm`
`application/wasm`). Pas de proxy `/app/` vers Django : le Service Worker
intercepte ces routes sous le préfixe du site. L'entrée utilisateur est le
répertoire publié, avec un `/` final.

Publier un bundle complet d'un seul coup (répertoire versionné puis changement
de la racine statique), avec `Cache-Control: no-cache` pour `sw.js` et
`config.json`. Ne pas mélanger les fichiers de deux constructions. Le cache
vérifie les SHA-256 du bundle à l'installation ; une installation incomplète
n'active pas la nouvelle version. Conserver l'ancien dossier publié pour
pouvoir réparer une publication, sans imposer un retour de données.

Le déploiement n'a pas besoin de COOP/COEP dans cette architecture. S3, SMTP,
pywebview, serveur WSGI réseau et moteur PDF ne sont pas embarqués. Le projet Pages PWA est distinct du projet Hugo ; leurs Service Workers et
ressources ne se recouvrent pas. Ils partagent toutefois origine et quota lorsque
le domaine unique est désactivé : conserver des contenus de confiance.
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
coupure électrique pour étendre la qualification ; ces retours ne bloquent pas
la publication dans le périmètre déclaré par PRODUCTION.md. #PWA6 sauvegarde
les fichiers modifiés après chaque
réponse et active leur manifeste commun, sans ZIP intermédiaire.
Web Lock et file exclusive du Worker sont indispensables ; seuls eux
justifient `DJANGO_ALLOW_ASYNC_UNSAFE` dans ce profil Pyodide.

## #PWA11 : médias lus à la demande

`lazy_media.js` conserve les répertoires et métadonnées MEMFS, mais remplace le
contenu des fichiers confirmés par les `File` des blobs OPFS immuables. Les
lectures synchrones sont déléguées à WORKERFS par tranches, sans cache maison.
Les chemins Python, Pillow, Django, les renommages de restauration et le format
ZIP commun restent utilisables. Ce n'est pas un montage OPFS en écriture.

Un média nouveau reste dans MEMFS pendant sa requête. Une modification en place
copie seulement le fichier concerné ; une troncature à zéro évite cette copie.
Après l'activation OPFS/IndexedDB, le Worker remplace ces buffers par des `File`.
Il refuse cette substitution si le média est encore ouvert : fermer les fichiers
dans les traitements Python. Les blobs actifs ne sont jamais modifiés en place.
Les droits passent toujours par Django ; aucun URL public OPFS n'est ajouté.

La réouverture vérifie chaque SHA-256 en JS, une photo à la fois, puis installe
ses métadonnées et son `File`, sans recopier les photos en Python. L'inventaire
réutilise les empreintes vérifiées. Le manifeste interne reste au format 2 ;
les anciens ZIP internes et publics sont repris par les parcours existants.
La première conversion des anciens instantanés ZIP décompresse encore dans MEMFS ;
les restaurations ordinaires passent désormais par les transferts #PWA12.
Actif/précédent/secours et nettoyage
restent régis par le même pointeur transactionnel.

**#PWA12 transfère les ZIP progressivement.** L'export et le secours écrivent
sur OPFS ; le téléchargement lit un `File` par flux. Le multipart et les fichiers
uploadés sont temporaires sur OPFS. Le validateur commun décompresse un média
à la fois vers un blob immuable, retenu jusqu'à confirmation ou annulation.
SQLite reste MEMFS. Voir [TRANSFERTS-OPFS.md](TRANSFERTS-OPFS.md).

Le module dépend des opérations de nœuds MEMFS/WORKERFS du runtime **Pyodide
314.0.7 épinglé**. Sa disponibilité est contrôlée au démarrage ; ne pas annoncer
une compatibilité universelle et requalifier lors d'un changement de runtime.
Voir [MEDIA-OPFS.md](MEDIA-OPFS.md) pour l'audit des interfaces, la décision et
les limites, et [QUALIFICATION.md](QUALIFICATION.md) pour les mesures. Les essais
terrain restent non bloquants.

La maintenance des dépendances et les contrôles avant publication sont décrits
dans PRODUCTION.md. Synchronisation, sauvegarde automatique hors
appareil, chiffrement et travail concurrent restent hors périmètre.
Le périmètre de qualification est explicite dans PRODUCTION.md.

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
Le job automatique **pwa-qualification** publie ce rapport, y compris en cas d'échec,
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

## Installation et usage quotidien (#PWA7)

La coque propose **Installer Petits Pas** lorsque le navigateur émet une offre
d'installation ; si elle est absente, l'aide décrit le menu Chrome/Edge et
Safari. Un refus n'empêche pas l'usage dans un onglet. Le manifeste garde le
préfixe de publication, un identifiant relatif stable et des PNG 192/512 ; une
icône Apple est déclarée. L'installation effective sur chaque OS reste à observer.
Les étapes de préparation sont annoncées, sans pourcentage artificiel ; version,
réseau indicatif, stockage protégé/non protégé et erreurs sont accessibles.
Le délai d'installation est borné, son échec ne laisse plus une attente infinie.
Une erreur propose de réessayer ou récupérer, sans effacer les données.

## Suivi commun des exports (#PWA8)

**Sauvegardes / transfert** ouvre le parcours commun, dont les droits de direction
restent vérifiés par Django. Le programme autonome et la PWA affichent la date du
**ZIP préparé**, pas celle d'un fichier effectivement conservé. Sans export ou
après sept jours, la direction reçoit un rappel discret. Aucun rappel n'est
ajouté au profil hébergé ni aux impressions.

`suivi.paquet_local.noter_export/suivi_export` enregistrent et lisent
`suivi-sauvegarde.json`, sans modèle ou migration SQL. Ce suivi est absent des
ZIP publics ; une restauration remet donc le rappel. En PWA ce fichier rejoint
le manifeste interne et son activation atomique après export ; ancien stockage
et anciens ZIP sans suivi restent lisibles. Une date absente, altérée ou future
est ignorée. Le secours ne marque pas un export de l'état actuel.

La feuille [ESSAIS-APPAREILS.md](ESSAIS-APPAREILS.md) permet les retours #PWA9
sans en faire une campagne bloquante. Le prompt du chantier Hugo et publications
est dans [AUDIT-SITE-PUBLICATIONS.md](AUDIT-SITE-PUBLICATIONS.md).

## #PWA8a : CI systématique et téléchargements repris

`pwa-prototype` et `pwa-qualification` s'exécutent dans chaque pipeline accepté
par les règles globales (branches et merge requests), en parallèle des autres
vérifications. Leurs échecs font échouer le pipeline. `pwa-publication` reste
manuelle sur main, avec une dépendance aux deux jobs réussis. Le contrôle du
statut exact du job dans le projet destinataire reste conservé.

Le cache CI `.cache/pwa/runtime-314.0.7/` est partagé par version. La deuxième
construction utilise ce runtime et les wheels de la première, sans nouveau
téléchargement Pyodide ou pip. Même sans cache GitLab, les deux constructions
d'un job réutilisent ses fichiers. Trois téléchargements au maximum sont
simultanés ; une erreur réseau temporaire est reprise jusqu'à quatre essais
(attentes de 1, 2 et 4 secondes). Les fichiers téléchargés sont remplacés
atomiquement, leur longueur est contrôlée lorsqu'elle est fournie et les
wheels WASM restent vérifiées avec les SHA du lock Pyodide. Une erreur de
certificat ou un HTTP permanent comme 404 échoue sans reprise ; TLS n'est
jamais désactivé. Une indisponibilité durable reste un échec explicite de CI.

Tests : `python3 -m unittest discover -s scripts -p test_construire_pwa.py`.
Les suites runtime/HTMX ne sont pas relancées pour cette correction du
constructeur : le bundle de distribution reste identique à #PWA7–8.

## #SP4 : école fictive dans un espace distinct

Le constructeur requiert désormais les dépendances Python du dépôt pour produire
le ZIP fictif (en CI, `requirements.lock`). La génération utilise une base
temporaire sans tables axes, compatible avec le profil local. Le bundle contient
`ecole-fictive.zip`, sa notice et `essai.html`, tous contrôlés par les empreintes
du Service Worker et du préparateur de publication.

Le mode d’essai est transmis par la coque dans les messages init/secours. Le
Worker configure le suffixe OPFS/IndexedDB avant toute lecture. Les noms
habituels restent inchangés ; le verrou commun impose un seul espace ouvert.
Le ZIP commun est validé avant son installation, seulement si l’espace d’essai
est vierge. Retour, relance, secours et mise à jour conservent leur espace ;
aucune restauration n’est effectuée pour revenir à l’école habituelle.

L’entrée `essai.html` n’existe pas dans les anciens bundles : un ancien Service
Worker ne transforme donc pas silencieusement ce lien en ouverture habituelle.
Publier puis appliquer la mise à jour pour rendre le bouton disponible. Cette
séparation protège du mélange involontaire des essais et du travail ; elle ne
protège pas contre les autres contenus de la même origine ou la suppression du
profil. Utiliser uniquement des données fictives dans les essais.

## #SP3a : référent HTTPS et protection CSRF

Le Service Worker transmet `Request.referrer` lorsqu’il n’est pas exposé dans
`Request.headers`, sans fabriquer de valeur si le navigateur l’a supprimée.
Les contrôles CSRF de Django restent actifs. Le banc sous `/petits-pas-pwa/`
utilise désormais HTTPS (`PWA_TEST_HTTPS=oui`, OpenSSL requis) avec un certificat
éphémère réservé aux essais. Il couvre les formulaires et actions HTMX, et
vérifie le refus des requêtes sans jeton ou avec un référent absent ou étranger.

## #SP5 : vérifier un ZIP dans une copie

Le formulaire local commun prépare un ZIP compatible dans un répertoire séparé.
Le Worker enregistre ses fichiers dans le suffixe `-apercu` avant la navigation
vers `apercu.html`, puis supprime le répertoire MEMFS préparé. Le runtime habituel
conserve son propre stockage. Le commit OPFS/IndexedDB réutilise le mécanisme
transactionnel existant ; une erreur n’ouvre pas une copie partielle.

La copie utilise ses comptes et les sessions du ZIP sont effacées avant ouverture.
L’impression, les modifications et l’export restent possibles avec les droits
habituels. Le retour ne restaure rien ; l’adoption passe par un export et la
restauration explicitement confirmée dans l’espace habituel.

## Versions et publication (#SP6)

La version applicative (tag commun ou `dev.<commit>`) est distincte de
l’empreinte technique du bundle, conservée pour les caches. Les nouveautés
embarquées sont celles de `CHANGELOG.org` au commit construit. La publication
reste manuelle après réussite des deux jobs PWA en CI ;
voir [PUBLICATION.md](PUBLICATION.md). Les programmes restent publiés sur
GitHub par la commande CLI, indépendamment de GitLab Pages.

## Version maintenue (#PWA13)

Le runtime courant est Pyodide 314.0.7/Python 3.14.2 ; SQLite et hashlib de base
sont désormais dans la bibliothèque standard. La dérivation des mots de passe
reste compatible avec Django natif par PyCryptodome. Les versions WASM sont
consignées dans config.json. Les transferts attendent jusqu'à quinze minutes,
avec arrêt du Worker et reprise de l'état confirmé si le résultat est incertain.
Les noms historiques du verrou, d'IndexedDB et des jobs Pages sont conservés ;
les nouveaux bundles portent l'identité `pwa.<empreinte>`. Voir PRODUCTION.md.

Pour vérifier une mise à jour depuis un ancien bundle `--test` réellement
construit (par exemple #PWA12/Pyodide 0.28.3), conserver ce répertoire et lancer :

```sh
PWA_OLD_BUNDLE=/chemin/bundle-ancien node scripts/verifier-pwa.cjs
```

Le banc crée l'école et un média fictifs dans l'ancien runtime, ferme l'onglet,
active la nouvelle version et vérifie connexion, base et média avant les
parcours courants. Les modèles d'images #J2 de main sont conservés ; les photos
nouvelles sont uniques depuis #J2d, sans recomprimer les anciens médias.
