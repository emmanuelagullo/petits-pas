# #PWA5 : qualification du prototype navigateur

Qualification réalisée le 3 octobre 2026 sur Chromium 138 headless/Linux
x86_64, avec Playwright 1.62.1. Aucune donnée réelle. Le scénario comporte
120 élèves répartis en six classes, le référentiel de départ et des traces
avec une image synthétique JPEG de 109 621 octets (environ 107 Kio), stockée
séparément pour chaque trace. Il n'évalue pas des milliers d'observations par
élève ou tous les référentiels disponibles.

## Mesures

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

## Reprises vérifiées

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

## Corrections et décision

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

## Reproduire

Voir `pwa/README.md`. Le script `scripts/qualifier-pwa.cjs` produit
`dist/qualification-pwa.json`. Le job manuel `pwa-qualification` publie ce
rapport sans livrer le bundle de test. La CI distante n'a pas été exécutée
pour cette livraison. La suite Django complète n'est pas relancée : aucun
modèle, migration, vue ou profil serveur/autonome n'est modifié par #PWA5.

Bundle testé : `pwa-prototype.0a02b3ece98eff2c`.
