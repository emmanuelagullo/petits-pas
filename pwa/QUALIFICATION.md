# Qualification du prototype navigateur

## #PWA5 : bilan historique du stockage ZIP

Qualification réalisée le 3 octobre 2026 sur Chromium 138 headless/Linux
x86_64, avec Playwright 1.62.1. Aucune donnée réelle. Le scénario comporte
120 élèves répartis en six classes, le référentiel de départ et des traces
avec une image synthétique JPEG de 109 621 octets (environ 107 Kio), stockée
séparément pour chaque trace. Il n'évalue pas des milliers d'observations par
élève ou tous les référentiels disponibles.

### Mesures

Cinq lectures du même écran de saisie par palier ; médiane dans le tableau.
Le temps inclut le pont Worker/WSGI et la persistance, mais pas le rendu visuel
ni tous les échanges du Service Worker. Le serveur de fichiers est local :
ce n'est pas une mesure de premier téléchargement sur le réseau d'une école.

| Photos | ZIP enregistré (Mio) | Lecture (ms) | Création du ZIP (ms) | Tas WASM alloué (Mio) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.05 | 298 | 16 | 71.9 |
| 30 | 3.18 | 412 | 129 | 71.9 |
| 90 | 9.46 | 662 | 353 | 86.2 |
| 140 | 14.69 | 872 | 546 | 86.2 |

Le tas WASM mesure une capacité allouée, **pas toute la RAM du navigateur**.
La mesure Linux PSS n'était pas accessible dans cet environnement : le rapport
indique `null`, sans l'assimiler à zéro. MEMFS, les copies JS, le cache, le
rendu et les autres processus empêchent de déduire un budget RAM complet de
la seule colonne WASM. Aucun poste ou tablette d'école n'est qualifié ici.

### Reprises vérifiées

- Avertissement visible à proximité de la limite, avec le volume du dernier
  état effectivement enregistré.
- Passage à 180 photos : la limite effective de 16 Mio refuse l'enregistrement,
  bloque le runtime et la réouverture retrouve les 140 photos confirmées.
- Quota de l'origine contraint par Chromium via DevTools : une écriture OPFS
  échoue réellement ; le dernier état reste lisible après réouverture. Ce
  n'est pas une injection de `QuotaExceededError` dans le code de l'application,
  ni un essai de remplissage physique du disque.
- SIGKILL du groupe du navigateur après `flush()` OPFS, avant activation du
  pointeur IndexedDB : l'état précédent est retrouvé.
- SIGKILL après activation du pointeur, avant réponse utilisateur : le nouvel
  état est retrouvé. Une opération sans réponse peut donc être enregistrée ;
  il faut vérifier son résultat après reprise avant de la répéter.
- Les reprises vérifient le SHA-256 de chaque fichier photo, passent
  `PRAGMA quick_check` et `foreign_key_check`, puis nettoient les instantanés
  OPFS orphelins.
- Aucune requête `/app/` n'est reçue par le serveur statique.

Une mise hors tension, l'éviction du profil, la perte du disque et le SIGKILL
ne sont pas des événements équivalents. Seul le dernier a été testé ici.

### Corrections et décision

La copie MEMFS du paquet remplacé lors d'une restauration est désormais
libérée **après** l'activation durable. Le secours OPFS reste conservé. Les
22 parcours navigateur de #PWA3/#PWA4 passent, avec une vérification de cette
libération après restauration. Les 18 tests du paquet autonome passent.

La coque montre le volume confirmé et avertit dès 13 Mio. La limite de
16 Mio est maintenue. Les pauses de qualification et la lecture des métriques
restent réservées aux bundles `--test` ; ils ne doivent pas être publiés.

**La reprise du prototype est suffisamment étayée pour poursuivre les essais
fictifs. Le stockage actuel ne convient pas encore à un carnet annuel complet
d'école.** Le seuil en nombre de photos dépend de leur taille : 140 photos
passées dans ce scénario ne constituent pas une garantie ou un quota scolaire.

Priorité #PWA6 : éviter le ZIP complet à chaque lecture et découpler la
persistance des médias tout en gardant une activation cohérente de la base et
des photos, ainsi que le format ZIP commun avec le mode autonome. Ensuite,
mesurer la RAM totale et la latence sur appareils d'école, qualifier Firefox,
Safari/Android, installation PWA, impression interactive et panne électrique.

### Reproduire

Voir `pwa/README.md`. Le script `scripts/qualifier-pwa.cjs` produit
`dist/qualification-pwa.json`. Le job manuel `pwa-qualification` publie ce
rapport sans livrer le bundle de test. La CI distante n'a pas été exécutée
pour cette livraison. La suite Django complète n'est pas relancée : aucun
modèle, migration, vue ou profil serveur/autonome n'est modifié par #PWA5.

Bundle testé : `pwa-prototype.0a02b3ece98eff2c`.


## #PWA6 : stockage incrémental — 4 octobre 2026

Même environnement Chromium 138/Linux x86_64 et Playwright 1.62.1, 120 élèves
fictifs en six classes et référentiel de départ. Les JPEG synthétiques de
107 Kio portent désormais un suffixe distinct : aucun partage de blob ne
réduit artificiellement le volume du scénario. Cinq lectures du même écran
par palier, même périmètre Worker/WSGI sans rendu visuel. Ce banc ne représente
pas un carnet annuel complet ni un appareil d'école.

### Mesures et évolution

| Photos | État avant compression, manifeste compris (Mio) | Lecture médiane (ms) | Inventaire médian (ms) | Octets écrits OPFS par lecture |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 1.02 | 272 | 7 | 0 |
| 30 | 4.16 | 266 | 7 | 0 |
| 90 | 10.46 | 264 | 7 | 0 |
| 140 | 15.69 | 279 | 8 | 0 |
| 300 | 32.46 | 270 | 8 | 0 |
| 550 | 58.71 | 281 | 10 | 0 |

La lecture à 140 photos passe d'environ 872 ms sous #PWA5 à 279 ms dans ce
banc. Avec 550 photos, elle reste autour de 281 ms. Les fichiers de médias
inchangés ne sont plus relus ni recompressés ; les 30 lectures mesurées ne
créent aucun blob/manifeste et ne changent pas le pointeur IndexedDB. Une
modification SQL réécrit la base, sans recopier les médias (régression dédiée).
Le ZIP complet est construit uniquement pour les exports demandés.

Les transferts HTTP binaires évitent les anciennes copies base64/JSON. Le
premier essai volumineux a fait tomber la page pendant l'export avec l'ancien
transport ; l'export/import complet passe avec des buffers transférables.

Le ZIP exporté de 550 photos pèse 57.59 Mio. Le tas WASM
alloué avant transfert est de 71.9 Mio et atteint 172.1 Mio après cet
aller-retour. **Ce n'est pas la RAM totale ni son pic** : MEMFS, les copies JS
et les autres processus ne sont pas comptés. PSS reste indisponible. La
limite de 64 Mio ne garantit donc pas la tenue en mémoire sur tablette.

### Cohérence et compatibilité vérifiées

- Export de 550 photos accepté par le validateur du paquet autonome ; import
  réel de ce ZIP dans la PWA par le formulaire commun, avec confirmation.
- Volume confirmé et avertissement à 52 Mio visibles.
- Tentative de 650 photos refusée par la limite de 64 Mio ; runtime bloqué,
  réouverture et retour aux 550 photos confirmées.
- Quota Chromium contraint : écriture OPFS réellement refusée, ancien état
  cohérent retrouvé.
- Remplacement d'une photo, suppression de son ancien chemin et modification
  SQL simultanées : SIGKILL avant activation retrouve la base **et** la photo
  anciennes ; SIGKILL après activation retrouve la base **et** la photo nouvelles.
- SHA-256 de chaque photo, `quick_check` et `foreign_key_check` après les reprises.
- Nettoyage exact des orphelins ; tous les fichiers conservés sont référencés
  par l'état actif, le précédent ou le secours. Les blobs partagés restent présents.
- Aucune requête métier transmise au serveur statique.

Les neuf contrôles du banc passent. Les 24 scénarios de régression passent,
avec migration réelle depuis un bundle #PWA5 stockant des ZIP, actualisation
explicite du runtime avec migration SQL, droits, impression, hors ligne,
restauration/annulation et export de secours avant version. Les 18 tests du
paquet autonome passent, ainsi que Hugo et les contrôles de syntaxe.

La suite Django complète et la CI distante ne sont pas exécutées : aucun
modèle, migration ou profil serveur/autonome n'est modifié. Les jobs manuels
existants reprennent les scripts mis à jour. Le bundle `--test` reste réservé
au banc ; la livraison ne publie aucun site ni données.

### Décision et suite

Le coût du ZIP par consultation est éliminé et la cohérence base/médias est
vérifiée lors des interruptions testées. La limite de travail passe à **64 Mio
avant compression, manifeste public compris**, avec 5 000 entrées maximum ;
l'envoi multipart est limité à 70 Mio. Les quotas navigateur peuvent refuser
une écriture avant ces seuils. L'espace physique inclut aussi les anciennes
versions et les ressources du runtime.

Les ZIP publics restent ceux du mode autonome. Le format interne OPFS change :
les versions antérieures de la PWA ne peuvent pas le relire. Exporter un ZIP
avant mise à jour et le garder pour un retour vers un runtime compatible.

La qualification demeure limitée aux données fictives. Priorité suivante :
mesurer mémoire totale, rendu et impression sur postes/tablettes d'école,
installation et éviction du stockage, puis panne électrique et autres moteurs.
Si la mémoire ne tient pas, sortir les médias de MEMFS ou rendre les gros
transferts progressifs, plutôt que relever simplement la limite. La base est
encore copiée et comparée à chaque requête, et entièrement persistée à chaque
modification ; une persistance SQLite par pages n'est pas acquise ici.

Bundle testé : `pwa-prototype.c940947442f0addd`. Rapport reproductible :
`dist/qualification-pwa.json`, généré par `scripts/qualifier-pwa.cjs`.

## #PWA7–8 — usage et sauvegardes (4 octobre 2026)

Les suites Chromium passent : 26 contrôles à la racine, 27 sous
`/petits-pas-pwa/`. Elles couvrent : coque à
390 pixels sans débordement, manifeste et PNG 192/512 accessibles, branche
`beforeinstallprompt` exercée par un événement simulé avec refus, navigateur
sans Web Locks refusé sans initialiser Django, version visible, export/date
retrouvée après redémarrage, import natif, photos, droits, impression, hors ligne,
interruption/quota injectés, mise à jour/migration SQL et récupération.
Il ne s'agit pas d'une installation réellement effectuée par un OS mobile.

20 tests du paquet local, 8 tests de publication et 6 tests Django ciblant les
sauvegardes locales passent ; aucun changement de migration. Hugo est construit.
La suite Django complète, le scénario 550 photos et les arrêts SIGKILL ne sont
pas relancés pour ce changement d'interface/suivi d'export. La mémoire totale
reste inconnue sur tablettes. L'algorithme de persistance reste celui de #PWA6 ;
le suivi local ajoute un fichier optionnel au manifeste interne, couvert par
la réouverture réelle après export, sans changer le format ZIP public.

La limite 64 Mio est maintenue et expliquée dans ESSAIS-APPAREILS.md.
Les retours terrain #PWA9 ne constituent pas un jalon bloquant pour poursuivre
ou publier le prototype ; ses limites restent annoncées, sans prétendre
valider toutes les plateformes ou un usage de production par ces seuls essais.

## #PWA8a — constructeur et règles CI

Les deux jobs PWA s'exécutent automatiquement et un échec est désormais
bloquant pour la CI. Cela concerne les bancs automatisés disponibles, pas la
feuille de retours terrain #PWA9, qui reste non bloquante.

Six tests simulent erreur TLS temporaire, réponse tronquée, cache altéré,
échec durable, certificat invalide, HTTP 404 et empreinte incorrecte. La
construction test puis distribution est vérifiée avec le runtime en cache et
les wheels de la première construction ; la reconstruction finale interdit
explicitement tout accès réseau Pyodide et utilise pip sans index. Le bundle
reste `pwa-prototype.e138e60d4cf2458f`, identique à #PWA7–8. Les scénarios
navigateur ne sont donc pas relancés. Les règles YAML et l'application du patch
sont vérifiées ; le comportement réel du planificateur GitLab et la qualité
réseau du runner restent à confirmer par le nouveau pipeline.

## #PWA11 : médias hors des buffers MEMFS — 6 octobre 2026

Base de travail : main `2ef1e9d37009afd5b31ceea89df7f37a7cdd9ad6`.
Runtime Pyodide 0.28.3, Chromium 138.0.7204.0/Linux x86_64, Playwright 1.62.1.
Même scénario de 120 élèves fictifs, six classes et JPEG synthétiques distincts
de 107 Kio. Aucun appareil d'école ni donnée réelle. Le banc conserve la limite
64 Mio et le format ZIP public. Choix et audit des interfaces dans
[MEDIA-OPFS.md](MEDIA-OPFS.md).

### Mémoire et consultations

| Photos | Médias (Mio) | Médias résidents MEMFS (Mio) | WASM alloué (Mio) | Tas JS utilisé Worker (Mio) | Backing stores JS Worker (Mio) | PSS Chromium total (Mio) | Lecture médiane (ms) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 71.88 | 13.67 | 112.65 | 456.17 | 145 |
| 30 | 3.14 | 0 | 71.88 | 14.08 | 113.84 | 457.58 | 141 |
| 90 | 9.41 | 0 | 71.88 | 13.86 | 118.67 | 461.14 | 133 |
| 140 | 14.63 | 0 | 71.88 | 14.75 | 115.91 | 455.52 | 153 |
| 300 | 31.35 | 0 | 71.88 | 15.83 | 116.06 | 456.49 | 163 |
| 550 | 57.48 | 0 | 71.88 | 15.58 | 117.84 | 453.23 | 154 |

Cinq lectures Worker/WSGI par palier, sans rendre tout le carnet. Aucune de ces
30 lectures n'écrit de blob/manifeste ni de pointeur. Les inventaires médians
restent entre 8 et 11 ms. Les nouvelles photos sont d'abord écrites dans MEMFS
pendant la requête ; les relevés sont pris **après** leur confirmation et
remplacement par les `File` OPFS. Ils ne mesurent pas le pic de cette écriture.

À la reprise des 550 photos, avant toute lecture Python de leur contenu :
**0 octet média résident**, 49.88 Mio WASM, 17.61 Mio de tas JS utilisé,
94.47 Mio de backing stores et 413.86 Mio de PSS pour tous les processus du
navigateur. Le compteur de lecture WORKERFS est nul à ce point : les SHA-256
ont été vérifiés en JS, une photo à la fois, et n'ont pas été passés à Python.
La reprise prend 7.86 s dans ce banc, runtime et ouverture compris.

Le ZIP commun de 550 photos fait **57.59 Mio**. Après export, réimportation et
confirmation réels : médias résidents nuls, mais **172.63 Mio WASM**, 19.60 Mio
de tas JS utilisé, 213.94 Mio de backing stores et **653.95 Mio PSS**. Le gain
sur les médias confirmés ne supprime donc pas les copies complètes des ZIP,
du multipart et de la décompression. Les 64 Mio restent inchangés.

`Runtime.getHeapUsage` est interrogé sur la cible CDP du **Worker**, pas sur la
coque. WASM et backing stores peuvent compter les mêmes octets ; ces colonnes
ne s'additionnent pas. La PSS somme les processus descendants du Chromium
propre au banc, sans Node ni serveur HTTP. Le banc résout maintenant les PID
hôte par `/proc/self/stat` lorsque `spawn` retourne des PID d'un espace de noms,
et refuse une somme partielle : cette correction rend ici la PSS disponible.
Les relevés sont des points de contrôle, pas des pics continus ni une garantie
sur tablette. Variations de GC et cache navigateur restent possibles.

### Preuve, cohérence et compatibilité

- Lecture Python, seek et Pillow `load()` sur un média confirmé OPFS.
- Création, modification `r+b`, troncature, ajout, renommage et suppression ;
  retour à zéro contenu média résident après chaque confirmation.
- Réponse média par la vue Django et refus des fonctions suspendues ; aucune
  route statique publique vers les blobs.
- 31 contrôles à la racine et 32 en HTTPS sous `/petits-pas-pwa/`, y compris
  espaces essai/aperçu, droits, CSRF, impression, export, restauration,
  annulation, fermeture et hors ligne, migration de version et secours.
- 10 contrôles du banc de volume : dépassement réel des 64 Mio, quota Chromium
  réellement contraint, SIGKILL avant/après activation avec remplacement et
  suppression de photo et changement SQL simultanés. Chaque reprise vérifie
  les SHA-256, `quick_check` et `foreign_key_check` ; nettoyage exact de l'union
  actif/précédent/secours, et aucune requête métier sur le serveur statique.
- ZIP de 550 photos accepté par le validateur autonome puis réimporté par le
  formulaire commun. Le format interne reste 2 et n'exige aucune conversion
  des installations #PWA6–#PWA10 ; les instantanés ZIP plus anciens conservent
  leur convertisseur. Leur migration depuis un ancien bundle n'est pas
  relancée ici ; leur première ouverture conserve les copies MEMFS temporaires.
- 20 tests du paquet autonome, 6 tests du constructeur et 18 tests Django
  ciblés installation/sauvegardes passent. Absence de migration, Hugo et syntaxe sont vérifiés pour la
  livraison ; aucun profil serveur/autonome ni modèle n'est modifié.

Bundle testé : `pwa-prototype.bbde00ed5d4a11f8`. Rapports générés par
`scripts/verifier-pwa.cjs` et `scripts/qualifier-pwa.cjs`. La CI distante, les
autres moteurs, les coupures électriques et les appareils d'école ne sont pas
exécutés ; leurs retours restent non bloquants. La suite Django complète n'est
pas relancée pour cette adaptation du seul profil navigateur.

La preuve permet de livrer #PWA11 sans nouvelle architecture de cache ni Worker
supplémentaire. La prochaine augmentation de capacité exige d'abord de réduire
les copies ZIP et les décompressions MEMFS, avec de nouvelles mesures.
