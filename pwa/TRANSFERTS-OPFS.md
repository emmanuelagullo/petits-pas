# #PWA12 : ZIP progressifs sur OPFS

## Choix et interfaces

#PWA11 conserve les médias confirmés dans OPFS avec lecture WORKERFS ; #PWA12
retire aussi les archives et les médias décompressés de MEMFS. Ce n'est pas un
montage général OPFS dans Pyodide. Les chemins Django restent MEMFS, avec les
mêmes vues et droits. Le format ZIP commun n'a pas changé.

`FileSystemSyncAccessHandle` est réservé au Worker dédié et aux fichiers OPFS.
Son ouverture est asynchrone, puis read/write/flush/close sont synchrones. Le
Worker ouvre donc les handles avant les appels Python. `OpfsFile`, petit objet
`io.RawIOBase`, prête à JS une vue du buffer Python pendant chaque opération,
sans copie persistante ni cache. Une extraction en générateur permet de revenir
à JS entre fichiers pour ouvrir/fermer les handles ; le programme autonome
consomme synchronement le même générateur. Aucun deuxième Worker, SharedArrayBuffer,
Asyncify ou bibliothèque ZIP supplémentaire.

Sources vérifiées le 6 octobre 2026 :
- [spécification File System](https://fs.spec.whatwg.org/#api-filesystemsyncaccesshandle) ;
- [MDN SyncAccessHandle](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle) ;
- [Python 3.13 zipfile](https://docs.python.org/3.13/library/zipfile.html) ;
- [Pyodide BufferProxy](https://pyodide.org/en/0.28.3/usage/api/js-api.html#pyodide.ffi.PyBuffer).

## Parcours et cohérence

Le Service Worker lit le multipart en blocs de 1 Mio au maximum et attend un
accusé de réception avant le suivant. La requête brute et les fichiers uploadés
vont dans deux temporaires OPFS. Le gestionnaire Django lit des tranches ; ses
contrôles CSRF, session et direction restent obligatoires. Les autres requêtes
et réponses HTML/médias conservent le pont existant.

L'export direction écrit directement le ZIP sur OPFS avec le code commun,
avec une copie par blocs de 1 Mio, puis transmet un `File`, pas un ArrayBuffer complet. Le SW sert son flux et
supprime le temporaire après consommation ou annulation. Le secours utilise
également un `File` ; son temporaire reste disponible pour le téléchargement.
Le bouton continue à vérifier le droit de direction en fonctionnement normal.
Aucune URL publique ne sert un blob OPFS indépendamment de Django.

L’extraction d’une classe utilise le même temporaire OPFS. La projection crée
une base SQLite vide depuis le schéma seul, puis les seules lignes sélectionnées.
Les médias autorisés sont lus directement vers le ZIP par blocs de 1 Mio, sans
copie préalable dans MEMFS ni subprocess. Les plafonds restent identiques.
Cette extraction ne renouvelle pas le rappel de sauvegarde complète.

Le validateur commun contrôle noms, empreintes, taille décompressée, migrations
et SQLite. Chaque média est extrait par blocs de 1 Mio vers un nouveau blob.
Après fermeture, le chemin de préparation est lié au `File`. Les blobs préparés
restent retenus pendant les consultations et jusqu'à confirmation/annulation.
La base et la clé sont préparées dans MEMFS. Une confirmation reprend le
pointeur transactionnel IndexedDB existant ; les blobs actifs, précédents et de
récupération ne sont jamais modifiés en place. Les références Python temporaires
sont remplacées par les fichiers confirmés **même si leur empreinte est identique**
avant suppression des doublons. Une annulation ne change pas l'école active.

Une fermeture perd la préparation non confirmée. À la reprise, le pointeur actif
reste la référence et le nettoyage supprime les blobs abandonnés non référencés.
Les répertoires de transfert utilisent des identifiants uniques ; leurs fichiers
normaux sont supprimés après requête, et les transferts interrompus ou le secours
après 24 heures, lors d'un transfert ultérieur. Ce délai préserve les téléchargements
encore en cours ; il n'est pas une sauvegarde. Un quota épuisé bloque le runtime
sans annoncer un état enregistré ; fermer puis rouvrir retrouve le dernier état
confirmé. Ne pas effacer les données du site pour libérer cette école.

## Compatibilité et limites

Les installations précédentes (ZIP format 1 et manifestes format 2) restent
lisibles ; aucune migration destructive OPFS/IndexedDB. Le premier démarrage
sur un ancien instantané OPFS au format ZIP charge encore cet instantané borné
par l'ancien plafond de 64 Mio, puis le convertit en manifeste/blobs. Les
ouvertures suivantes utilisent les fichiers séparés. Le petit ZIP de l'école
fictive initiale est également chargé comme auparavant. Les ZIP anciens restent
communs à PWA, Linux et Windows. Les profils serveur et autonome gardent leurs
handlers et limites : leur export utilisait déjà TemporaryFile + FileResponse
sur disque natif, et leur import les temporaires Django puis les fichiers natifs.
La limite de 64 Mio était propre à la PWA, pas aux binaires Linux/Windows.

La nouvelle borne de qualification est 256 Mio décompressés/état, manifeste
compris, 5 000 entrées et 64 Mio par fichier/base. Le plafond individuel reprend
le maximum qu'autorisaient les anciens paquets de 64 Mio, sans recompression
silencieuse. Un ZIP avec un répertoire central de plus de 2 Mio est refusé avant
son allocation complète ; ce cas ne provient pas du producteur commun. Le
multipart est borné à 270 Mio avec son enveloppe. L'alerte débute à 205 Mio.
L'augmentation dépend des mesures consignées dans QUALIFICATION.md ; elle ne
supprime ni les quotas navigateur ni la mémoire SQLite. Les ressources du
runtime ne sont pas comprises dans le contenu du paquet.

Un import conserve temporairement requête + archive uploadée + médias extraits,
ainsi que les états actif/précédent/secours. Prévoir plusieurs fois la taille du
paquet en espace disque ; aucun quota de stockage garanti par l'application.
Une copie de vérification dans un autre espace peut recopier un média à la fois
via JS. Le démarrage vérifie également un média à la fois par SHA-256 JS. La
lecture d'une réponse média, le décodage Pillow, une modification ou un upload
d'image peuvent encore matérialiser **le fichier concerné** ; les pixels décodés
peuvent dépasser largement sa taille compressée. SQLite et sa copie cohérente
restent MEMFS. Le ZIP central et les manifestes gardent des métadonnées Python.
Les requêtes non multipart restent assemblées en mémoire (70 Mio maximum).

Le tas WASM est une capacité allouée, le tas/backing storage CDP un compteur JS,
et la PSS Linux une mesure globale des processus Chromium. Ils se recouvrent et
ne doivent pas être additionnés. Les mesures ponctuelles ne prouvent pas un pic
absolu ni une consommation identique sur Safari, Firefox ou tablette.

## Statut et suite

#PWA12 lève le principal plafond dû aux copies ZIP. Tout logiciel garde des
limites : leur disparition totale n'est pas un critère de sortie du prototype.
Une appellation « application navigateur » peut accompagner une version maintenue,
avec périmètre de navigateurs déclaré, récupération et mise à jour qualifiées,
versions/dépendances suivies et documentation d'exploitation cohérente. La
décision de diffusion sur données réelles reste explicite ; ce chantier ne la
prend pas automatiquement. Les retours d'appareils d'école restent non bloquants,
sans campagne terrain obligatoire. SQLite sur disque pourra constituer un
chantier séparé si la taille de la base devient la contrainte mesurée.
