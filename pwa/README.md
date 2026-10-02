# #PWA1 + #PWA2 : prototype navigateur

Expérience isolée, réservée aux données fictives. Elle ne remplace aucun des
profils serveur ou autonome. Base de départ : `main` au commit `647ae36`.

## Essayer

Python 3 avec pip et accès Internet sont nécessaires à la construction :

```sh
python3 scripts/construire-pwa.py
python3 -m http.server 8000 --directory dist/pwa
```

Ouvrir **http://localhost:8000/** dans Chromium récent, dans un profil dédié.
Le site doit occuper la racine d'une origine dédiée. En dehors de localhost,
HTTPS est obligatoire. Tout le dossier `dist/pwa` peut être servi par un
hébergement statique ; aucun serveur Python n'est nécessaire à l'utilisation.
Le premier téléchargement exige Internet. Ensuite le navigateur conserve le
runtime et les ressources. Une école créée ici appartient à ce profil et à
cette origine, pas à l'ensemble de l'ordinateur.

L'écran existant du mode autonome permet de créer l'école et son compte.
Les mots de passe restent hachés par Django avec PBKDF2 ; CSRF et autorisations
Django restent actifs. Il faut se reconnecter après fermeture/rechargement.
Ne pas déplacer l'origine ni actualiser le bundle avec une école à conserver :
la reprise entre versions n'est pas qualifiée et est refusée.

## Vérification reproductible

Node.js et Chromium Playwright sont nécessaires :

```sh
npm install --prefix pwa
npx --prefix pwa playwright install chromium
python3 scripts/construire-pwa.py --test
node scripts/verifier-pwa.cjs
```

`PWA_CHROMIUM=/chemin/chromium` permet d'utiliser un Chromium installé.
Les caches facultatifs `--runtime DOSSIER` et `--wheels DOSSIER` évitent de
retélécharger les dépendances à la construction. Le test crée son propre
serveur statique et un contexte navigateur temporaire ; aucune donnée réelle
n'est nécessaire. Résultats générés dans `dist/pwa/resultats-tests.json`.

**Ne jamais publier une construction `--test`** : elle expose une commande
Python arbitraire aux essais automatisés. Reconstruire sans cette option.

## Ce qui est réalisé

- #PWA1 : CPython/Pyodide 0.28.3 et Django 6.1.1 dans un Worker dédié ;
  vraies migrations, vues, templates et formulaires HTMX du dépôt.
- Service Worker servant les ressources et transportant les requêtes `/app/`
  par MessageChannel vers le shell propriétaire et son Worker WSGI. Le shell
  reste ouvert autour d'une iframe pour que les navigations Django ne détruisent
  pas le runtime. `SAMEORIGIN` remplace `DENY` seulement dans ce profil.
- Cookies Django virtuels en mémoire dans Python ; le pont conserve le CSRF
  pour HTMX. Le profil local existant fournit la gestion côté école.
- SQLite de CPython en mémoire, avec `sqlite3.backup()` puis instantané ZIP
  cohérent comprenant base, clé locale et médias. Pillow WASM traite les photos.
- #PWA2 expérimental : écriture d'un nouvel instantané OPFS, `flush()` et
  fermeture, puis activation du pointeur avec transaction IndexedDB de durabilité
  stricte. La réponse utilisateur attend cette activation. L'ancien instantané
  est conservé jusqu'au succès suivant. Une erreur d'enregistrement bloque le
  runtime ; une réouverture reprend le dernier état confirmé.
- Un Web Lock interdit deux runtimes concurrents. La file du Worker est
  exclusive ; cela justifie ici `DJANGO_ALLOW_ASYNC_UNSAFE`, puisque Pyodide
  fournit une boucle active même pour les appels synchrones. Ne pas supprimer
  cette sérialisation ni réutiliser ce réglage dans le serveur standard.
- Export ZIP par la fonction **commune du mode autonome** : base SQLite,
  clé, médias et manifeste de sommes de contrôle. Restauration PWA bloquée.

Cette approche n'est **pas** un branchement de SQLite WASM/OPFS sur l'ORM Django.
Elle conserve le pilote SQLite natif de Pyodide et persiste des instantanés.
Cela permet de tester le métier sans inventer un nouveau backend SQL.

## Limites et suites

La base et tous les médias résident aussi en mémoire. L'instantané est limité
à 16 Mio compressés, et est refait après chaque requête, même une lecture
(session/messages peuvent écrire). Ce choix privilégie la simplicité de
l'expérience ; il n'est pas adapté à un gros carnet. Il faut mesurer RAM,
latence de sauvegarde et volumes réalistes avant d'envisager un pilote OPFS
plus fin ou des médias séparés avec protocole de validation cohérent.

Le cache est vérifié par SHA-256 à l'installation ; ceci détecte un bundle
incohérent mais n'authentifie pas un hébergeur compromis. Le stockage local
n'est pas chiffré. La protection demandée par le bouton du navigateur ne
remplace pas une sauvegarde externe. Effacement du profil ou changement
d'origine suppriment l'accès aux données.

PDF, restauration, import entre versions, synchronisation et multi-onglet
actif restent hors périmètre. Les liens de PDF renvoient 501 ; les POST de
restauration sont refusés avant d'appeler les opérations de fichiers du mode
bureau. Aucun accès S3 ni SMTP n'est nécessaire. Pywebview, serveur WSGI réseau
et moteur PDF ne sont pas embarqués. Pyodide, wheels et versions Django doivent
être requalifiés et maintenus avant production.

Le manifeste permet l'installation PWA selon le navigateur ; cette expérience
n'a pas qualifié les parcours d'installation sur tablette. Pas de preuve de
résistance à une coupure électrique : les essais injectent des erreurs au
point de validation et ferment réellement la page. Safari, Firefox, Android,
quota réel, gros médias et arrêt brutal du processus doivent être testés.

Suite proposée : #PWA2b, mesurer ces cas et le budget mémoire ; #PWA3, partager
le format et la validation d'import avec le paquet autonome en remplaçant
uniquement l'activation propre à chaque plateforme ; #PWA4, alternative PDF,
protocole de mise à jour/récupération, essais sur appareils d'école et déploiement
statique pilote. Ne pas promouvoir le prototype en utilisation réelle avant
ces étapes.

## Résultats obtenus le 2 octobre 2026

Chromium 138 headless, Playwright 1.62.1, Linux, profil temporaire, données
fictives : les 12 scénarios du script passent. Dernière exécution : premier
chargement 17,1 s, relance hors ligne avec reconnexion 10,2 s. Les essais
précédents donnaient 13–16 s au premier lancement. Ce ne sont pas des mesures
sur un réseau ou une tablette d'école. Bundle : 23,2 Mio de fichiers avant
compression HTTP, hors données locales.

L'installation de l'école, un clic HTMX enregistrant une compétence, le refus
CSRF, l'ajout d'une photo, son accès autorisé, l'export ZIP, le refus du deuxième
onglet, la reprise hors ligne, les erreurs de validation et quota injectées,
l'intégrité SQLite et la fermeture/réouverture sont vérifiés. Le serveur
statique ne reçoit aucune requête `/app/` pendant ces parcours.

Les 17 tests natifs du paquet autonome passent également ; aucune migration
n'est créée (`makemigrations --check --dry-run`). Syntaxes Python/JS et patch
vérifiés. La suite Django complète et Hugo ne sont pas exécutés : le changement
est isolé dans le profil prototype et ne modifie ni modèles ni site public.
La validation des autorisations reste limitée aux parcours du test, sans
prétention de couvrir toute la matrice de droits.
