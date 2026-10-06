# #PWA13 : application navigateur maintenue

La PWA a vocation à être utilisée en production sur un ordinateur individuel,
avec plusieurs comptes qui se relaient. Elle conserve les droits Django et les
ZIP communs au programme autonome. Elle n'est pas un service partagé : aucun
travail simultané sur plusieurs appareils, aucune synchronisation ni sauvegarde
automatique extérieure à l'appareil.

## Périmètre pris en charge

| Environnement | Garantie de cette livraison |
| --- | --- |
| Chromium desktop / Linux, HTTPS ou localhost, profil ordinaire dédié | Bancs racine et HTTPS `/petits-pas-pwa/`, hors ligne, impression Chromium, reprises et transferts volumineux |
| Chrome / Edge desktop sur d'autres systèmes | Même famille de moteur, mais essais de cette livraison non exécutés sur Windows/macOS ; qualification à étendre avant de les annoncer vérifiés |
| Firefox, Safari, Android, iPad | Pas encore qualifiés pour la production de cette version ; présence des API seule insuffisante |
| Navigation privée, profil temporaire ou effacé automatiquement | Inadapté à la conservation d'une école |

Utiliser une version de navigateur entretenue. Chromium 138 est la référence
reproductible du banc, pas une recommandation de conserver un navigateur ancien.
Le contrôle au démarrage vérifie HTTPS, Service Worker, Web Locks et OPFS ; dans
le Worker dédié, il écrit/lit/flush/ferme puis supprime un petit fichier distinct,
vérifie FileReaderSync, IndexedDB et SHA-256 avant de lire les données de l'école.
Il ne prouve ni un quota futur ni la disponibilité de toute la RAM.

Les API OPFS synchrones sont réservées aux Workers dédiés selon
[MDN](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle).
La [compatibilité de Pyodide](https://pyodide.org/en/314.0.7/usage/index.html)
ne vaut pas qualification de l'ensemble Django/OPFS/impression Petits Pas.

## Transferts et mémoire

Le budget d'une opération, attente dans la file exclusive comprise, est de
**15 minutes** ; le transport Service Worker attend **16 minutes** pour laisser
la coque transmettre l'erreur. Ce budget donne une marge sur le transfert de
241 Mio mesuré en quelques dizaines de secondes, sans garantir tous les postes.
Toutes les opérations partagent ce budget : une lecture derrière un long export
ne doit pas expirer après deux minutes. La coque indique la durée d'attente,
sans prétendre connaître un pourcentage ou prouver que Python progresse.
Le Worker peut rester occupé par une compression synchrone pendant cette durée.

En cas d'expiration, la coque arrête le Worker, masque l'application et demande
une réouverture. Aucun nouvel essai automatique de saisie : une activation
IndexedDB peut avoir précédé l'interruption. La réouverture vérifie le dernier
état confirmé. Le délai d'installation du Service Worker reste distinct (deux
minutes, avant ouverture du runtime). Le téléchargement du ZIP, une fois la
réponse prête, est un flux du navigateur sans nouveau délai applicatif.

Les plafonds restent **256 Mio** décompressés, **5 000 entrées**, **64 Mio** pour
la base ou un fichier. SQLite, son backup et le traitement d'une image restent
en mémoire. Un fichier de 64 Mio n'est pas une promesse de décoder n'importe
quelle image : la politique #J2 borne aussi les octets et les pixels. Les images
normalisées sont uniques depuis #J2d ; les médias anciens ne sont pas
recompressés. Le banc de 2 300 JPEG distincts mesure un volume stocké,
pas un quota de traces par école.

Les mesures #PWA12 distinguent capacité du tas WASM, tas/buffers JS du Worker et
PSS de tous les processus Chromium ; ces compteurs ne s'additionnent pas.
Le maximum PSS observé de 809 Mio pour le transfert de 241 Mio n'autorise pas à
promettre le fonctionnement sur une tablette à faible mémoire. Les mesures du
runtime de #PWA13 sont dans QUALIFICATION.md. Le quota local et les états
actif/précédent/secours ainsi que les temporaires requièrent de l'espace disque
supplémentaire ; voir TRANSFERTS-OPFS.md.

## Dépendances et entretien

Le runtime est épinglé à **Pyodide 314.0.7 / Python 3.14.2**, avec ses wheels
WASM (dont Pillow 12.2.0 et PyCryptodome 3.23.0). Django 6.1.1 est la version maintenue indiquée au
6 octobre 2026 sur [le site Django](https://www.djangoproject.com/download/).
Le constructeur consigne les versions réellement incluses dans `config.json`.
Python 3.14 retire les fonctions OpenSSL de hashlib. `pwa/crypto.py` fournit
PBKDF2 et scrypt par les [fonctions natives de PyCryptodome](https://www.pycryptodome.org/src/protocol/kdf),
sans changer les hashers Django, leur coût ou les mots de passe importés.
Les vecteurs SHA-1/256/512, UTF-8, longueurs étendues et scrypt sont comparés
au runtime natif dans le banc. Les algorithmes nécessitant un module optionnel
absent (par exemple Argon2/bcrypt) ne sont pas ajoutés ; les sauvegardes du
profil ordinaire utilisent les hashers communs embarqués. Les profils serveur/autonome gardent hashlib.

Le constructeur refuse un cache de l’ancien ABI et retire les fichiers runtime
obsolètes du bundle reconstruit. Le Worker vérifie aussi la version exportée
par le moteur avant son chargement : un cache mélangé ne doit pas ouvrir l’école.

Les versions du lock serveur et celles des wheels Pyodide sont différentes ;
mettre à jour requirements.lock ne corrige pas Pillow dans la PWA.

Pillow 11.3 du précédent runtime est concerné notamment par
[l'avis PSD](https://github.com/python-pillow/Pillow/security/advisories/GHSA-cfh3-3jmp-rvhc)
et [les coordonnées imbriquées](https://github.com/python-pillow/Pillow/security/advisories/GHSA-5xmw-vc9v-4wf2).
Le nouveau runtime apporte leurs correctifs. Pillow 12.2 reste antérieur à 12.3 :
les décodeurs de la PWA sont limités dès chargement à JPEG/PNG/WebP, y compris
pour ImageField Django. Le normaliseur commun demande explicitement ces formats
avant parsing. EPS/PSD/JPEG2000/GD/AREA et les chargeurs de polices ne sont pas
des entrées de Petits Pas. Les coordonnées de redimensionnement/copie sont
calculées par l'application après contrôle des dimensions ; aucun script,
filtre arbitraire ou coordonnées utilisateur n'est exécuté. Ce périmètre réduit
les chemins exposés ; il ne remplace pas l'entretien du runtime et des codecs C.

Avant chaque publication, consulter les avis
[Pillow](https://github.com/python-pillow/Pillow/security/advisories),
[Django](https://docs.djangoproject.com/en/6.1/releases/security/) et les
[versions Pyodide](https://pyodide.org/en/stable/project/changelog.html).
Corriger une vulnérabilité applicable avant promotion. Requalifier les bancs
après changement de runtime (MEMFS/WORKERFS et FFI) ou de codec : les dépendances
ne sont jamais mises à jour silencieusement dans une publication existante.

## Publication et exploitation

La publication manuelle promeut les octets contrôlés du même commit/pipeline,
après les deux jobs PWA obligatoires et le démarrage du bundle final sans hooks
de test. Un tag avec notes de version identifie la release ; `dev.<commit>`
identifie les candidats sur main. Le nom historique du job `pwa-prototype`,
du verrou et d'IndexedDB est conservé pour la procédure Pages et la reprise des
installations : il ne décrit plus le statut du produit. L'identité des nouveaux
bundles commence par `pwa.`. Ne pas mélanger les fichiers d'anciennes constructions.

Conserver l'adresse et le profil, protéger le poste et le ZIP, garder une copie
hors appareil et vérifier sa restauration dans une copie indépendante. La
persistance accordée par le navigateur protège de l'éviction automatique, pas
de l'effacement volontaire, d'une panne ou de l'accès au profil. OPFS et ZIP ne
sont pas chiffrés ; le secours accessible au propriétaire du profil ne constitue
pas une nouvelle permission de direction. Les applications sur la même origine
doivent rester de confiance. Préparer la protection des données avec l'école
comme pour le programme autonome.

Le format interne OPFS reste 2, avec reprise des installations précédentes et
conversion des anciens instantanés ZIP par leur convertisseur existant. #PWA13
n'ajoute aucune migration SQL ; celles des images #J2 de main restent appliquées
par le parcours commun. Les médias existants sont conservés sans recompression.
Les comptes ordinaires et les ZIP gardent leur compatibilité PWA/autonome.

Cette livraison prépare la version de production ; elle ne crée ni tag, ni
publication distante et ne change pas les anciennes versions déjà servies.
Les notes de la version effectivement publiée et son aide font référence.
Les tests utilisent exclusivement des données fictives. Les retours terrain
restent non bloquants ; une campagne en école n'est pas une condition préalable
à la publication sur le périmètre déclaré.
