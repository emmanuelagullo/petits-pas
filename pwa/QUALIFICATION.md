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
