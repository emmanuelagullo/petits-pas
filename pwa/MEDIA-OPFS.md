# #PWA11 : liaison synchrone et choix — 6 octobre 2026

## Audit court des interfaces officielles

| Possibilité | Capacités et obstacle | Décision |
| --- | --- | --- |
| `mountNativeFS()` Pyodide 0.28.3 | Monte un `FileSystemDirectoryHandle`, mais exige `syncfs()` ; sa synchronisation n'est pas la preuve d'une lecture OPFS sans copie mémoire. | Ne pas le substituer au protocole transactionnel. |
| `FileSystemSyncAccessHandle` | Lectures/écritures/seek par position synchrones dans un Dedicated Worker ; obtenir le fichier et créer le handle restent asynchrones. Aucun adaptateur POSIX Django/Pillow automatique. Les handles ouverts verrouillent les fichiers. | Conserver les handles courts existants pour écrire/flush/fermer les nouveaux blobs. Éviter un pool de handles ou un second Worker. |
| WORKERFS avec `File` OPFS | Emscripten documente des lectures synchrones de `File`/`Blob` dans un Worker sans copie complète ; système en lecture seule. Pyodide 0.28.3 embarque effectivement WORKERFS et son lecteur `FileReaderSync`. | Réutiliser cette lecture pour les blobs immuables, et MEMFS seulement pour les modifications en cours. |
| Montage OPFS natif ou WasmFS | Aucun montage OPFS direct complet n'est établi pour notre runtime épinglé. Changer de runtime/FS n'est pas une correction ciblée. | Hors de ce chantier. |

Sources consultées le 6 octobre 2026 :

- [Pyodide 0.28.3 : système de fichiers](https://pyodide.org/en/0.28.3/usage/file-system.html), notamment montage natif et synchronisation.
- [Emscripten : WORKERFS et FS](https://emscripten.org/docs/api_reference/Filesystem-API.html#workerfs).
- [WHATWG : File System](https://fs.spec.whatwg.org/), `getFile`, création asynchrone et verrou exclusif des accès synchrones.
- [MDN : FileReaderSync](https://developer.mozilla.org/en-US/docs/Web/API/FileReaderSync/readAsArrayBuffer).
- [Chrome DevTools Protocol : Runtime](https://chromedevtools.github.io/devtools-protocol/tot/Runtime/), compteurs de tas et backing stores.

## Preuve et intégration

La preuve ciblée du banc `verifier-pwa.cjs` lit une photo fictive déjà confirmée
avec Python puis Pillow (`load()`, lecture et seek), crée un fichier, le modifie
en `r+b`, le tronque, ajoute des octets, le renomme et le supprime. Après chaque
confirmation, `residentMediaBytes` doit être nul. Le même banc sert le média par
la vue Django autorisée et refuse un compte dont les fonctions ont été suspendues.
Les reprises et les interruptions sont vérifiées par les deux bancs existants,
sans campagne préalable sur appareils d'école.

L'intégration tient dans `lazy_media.js` : des nœuds MEMFS réguliers conservent
stat, noms, répertoires, suppression et renommage ; leurs lectures appellent
WORKERFS sur le `File`. Une écriture matérialise seulement le média concerné,
la troncature à zéro crée un buffer vide. Il n'y a ni cache de lectures, ni LRU,
ni pool de handles. Cette adaptation utilise des opérations internes Emscripten :
les bancs, le runtime épinglé et sa requalification sont indispensables.
Ce n'est pas une promesse d'API OPFS/POSIX standard.

Les fichiers doivent être fermés au point de confirmation. Une ouverture encore
vivante lors de la substitution bloque le runtime plutôt que masquer une
écriture. Les chemins existants restent réguliers, sans liens symboliques qui
feraient refuser un ZIP par le validateur commun.

La confirmation conserve le protocole format 2 : nouveaux blobs flush/fermés,
manifeste immuable puis transaction IndexedDB stricte. Après confirmation, les
buffers des médias sont remplacés par leurs `File`. Le précédent et le secours
restent protégés par l'union des références. Une erreur avant activation retrouve
l'ancien état ; une erreur après activation retrouve le nouveau. Aucun serveur
ou URL statique n'accède directement aux fichiers de l'école.

## Mémoire, ZIP et limites

Le démarrage relit encore tous les médias pour vérifier leur SHA-256, **un à la
fois en JS**, sans les passer à Python. Il n'est donc pas indépendant du volume
en durée ni exempt de buffers transitoires. Une lecture Python/Pillow utilise
les tranches demandées et ses buffers de décodage. Une requête qui importe ou
crée plusieurs photos conserve ses écritures jusqu'au point de confirmation.
Les écritures directes hors stockage Django doivent toujours invalider
l'inventaire ; le protocole Python de test force cet inventaire.

Les copies restantes sont explicites :

| Parcours | Copies encore complètes |
| --- | --- |
| Export courant | ZIP temporaire MEMFS, assemblage WSGI en `bytes`, conversion JS ; transfert du buffer sans copie base64. |
| Export de secours | `BytesIO`, valeur `bytes`, conversion JS. |
| Import, installation d'un ZIP, copie à vérifier | Corps JS/multipart, corps Python/temporaires d'upload, paquet décompressé MEMFS, inventaire et blobs nouveaux jusqu'à confirmation. |
| Ancien instantané ZIP interne | Archive et paquet décompressé MEMFS lors de sa première conversion ; médias libérés après confirmation. |

Le format public et les fonctions serveur/autonome ne changent pas. Les anciens
ZIP et manifestes internes 2 restent compatibles. SQLite reste MEMFS, avec
copie `backup()` et SHA-256 à chaque requête. Aucun autre profil n'est modifié.

**64 Mio de paquet avant compression, 70 Mio de multipart, 5 000 entrées et
alerte à 52 Mio restent cohérents avec le banc existant, mais ne sont pas une
garantie de RAM sur tablette.** Les gros transferts font encore augmenter le
tas WASM, qui ne rétrécit pas ensuite. Le runtime statique et les états OPFS
précédents/secours consomment en plus mémoire et espace. La prochaine extension
de capacité doit commencer par des ZIP progressifs et des répertoires de
décompression hors MEMFS ; relever le plafond maintenant déplacerait le problème.

Les métriques séparent capacité WASM, octets des médias résidents MEMFS,
tas JS du Worker (`usedSize`, `totalSize`, `backingStorageSize`) et PSS de
l'ensemble des processus Chromium. Les backing stores et WASM peuvent se
recouvrir : ne pas additionner ces compteurs. Ce sont des relevés aux points
de contrôle, pas des pics continus. La PSS manque si `/proc` ne permet pas
une mesure complète. Voir `QUALIFICATION.md` pour les résultats reproductibles.

Chromium/Linux est le moteur effectivement essayé. OPFS, WORKERFS et
`FileReaderSync` sont contrôlés au démarrage ; Firefox, Safari et appareils
d'école restent des compatibilités à observer, pas des conditions pour poursuivre.
L'absence d'une API bloque l'ouverture sans effacer ni recréer une école.
Le Service Worker, la racine, `/petits-pas-pwa/`, les espaces essai/aperçu,
l'authentification et les contrôles d'image gardent leurs parcours actuels.

## Requalification #PWA13

L'audit ci-dessus décrit le choix initial avec Pyodide 0.28.3. La version
maintenue passe à Pyodide 314.0.7 ; les bancs Pillow/Django, mutations de fichiers,
transferts et interruptions sont relancés. Le choix WORKERFS/MEMFS et le format
interne restent identiques. Voir PRODUCTION.md et QUALIFICATION.md pour la
version courante, les dépendances et le périmètre effectivement qualifié.
