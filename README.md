# Petits Pas

Petits Pas est une application libre de suivi des apprentissages en école
maternelle. Elle vise à offrir aux équipes pédagogiques un outil simple pour
documenter les observations, préparer les bilans et produire les carnets
individuels remis aux familles.

Le projet est en cours de développement. Les environnements de démonstration
et les supports publics utilisent exclusivement des données fictives.

## Développement local

Les procédures locales et les profils de déploiement sont décrits dans
`DEPLOIEMENT.org`, `ATELIER-PEDAGOGIQUE.org` et `REPRODUCTIBILITE.org`.

### Application locale (#L1–L2)

Avec les dépendances Python du projet installées, dans le shell Guix habituel,
ajouter `python-pygobject` et `webkitgtk-for-gtk3` au `use guix` de `.envrc`.
PyWebView sous Linux requiert PyGObject et l'API `WebKit2` 4.1 de WebKitGTK.
Le paquet `webkitgtk` seul n'expose pas cette API. Recharger `direnv`, puis
créer un environnement Python qui voit les paquets Guix :

```sh
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-local.txt
python -c "import gi; gi.require_version('WebKit2', '4.1'); from gi.repository import WebKit2"
python scripts/lancer-local.py
# Ou, pour un autre emplacement :
python scripts/lancer-local.py --paquet /chemin/vers/mon-paquet
```

Sur un paquet neuf, la fenêtre ouvre **Installer Petits Pas** : elle crée
l'école, un premier compte personnel de direction et la trame pédagogique
provisoire. La même fenêtre propose ensuite la connexion ordinaire. Sur un
paquet déjà initialisé, elle ouvre directement la connexion et ne modifie ni
les comptes ni le référentiel. Le formulaire est inaccessible dans les
déploiements serveur ou dès qu'une école ou un compte existe dans la base.

La commande facultative `--creer-ecole "Mon école" --commune "Ma commune"`
utilise la création d'école existante, charge
`referentiel/trame-cycle1.yaml` (une trame pédagogique provisoire) et affiche
les identifiants initiaux dans le terminal. Elle refuse d'ajouter une seconde
école dans ce paquet. Pour un autre chemin, lui passer aussi `--paquet`.
Ne lancer l'initialisation qu'une fois et conserver les mots de passe affichés.
Si une école a été créée avec la première version de #L1, charger la trame
explicitement, sans recréer l'école :

```sh
python scripts/lancer-local.py --charger-referentiel
```

Cette commande met à jour les compétences de la trame par code ; elle ne
s'exécute pas automatiquement lors des lancements suivants, afin de ne pas
réinitialiser les choix pédagogiques de l'école.

Le lanceur ouvre PyWebView sur Django, lié uniquement à `127.0.0.1` sur un
port libre. Fermer la fenêtre arrête le serveur. Par défaut, les nouveaux
paquets résident sous `~/.local/share/petits-pas/paquet-autonome/` (ou sous
`$XDG_DATA_HOME/petits-pas/paquet-autonome/` si cette variable est définie),
hors du dépôt : une nouvelle extraction ou mise à jour du code conserve ainsi
les données. Le chemin se règle par `PETITS_PAS_PAQUET_AUTONOME` ou `--paquet`
(prioritaire). Un chemin relatif est interprété depuis le répertoire de
lancement. Le paquet contient `carnet.sqlite3`, `media/`, `secret-key`, les
éventuelles `sauvegardes-migrations/`, et `staticfiles/` (recréé depuis le
code). Le courrier est désactivé.

**Paquet créé avec #L1 dans le dépôt :** fermer la fenêtre, puis le copier
explicitement vers le nouvel emplacement par défaut :

```sh
python scripts/lancer-local.py --paquet ./paquet-autonome \
  --copier-paquet "${XDG_DATA_HOME:-$HOME/.local/share}/petits-pas/paquet-autonome"
python scripts/lancer-local.py
```

La copie vérifie la base SQLite et conserve le paquet d'origine. L'ancienne
option `--deplacer-paquet` reste acceptée pour les commandes déjà utilisées.
La copie ne remplace jamais une destination existante. Le lanceur refuse de créer un paquet
vide à l'emplacement par défaut s'il détecte encore l'ancien paquet dans le
dépôt : il affiche la commande de transfert. Après vérification du nouveau
paquet, l'ancien peut être archivé ou supprimé manuellement pour éviter de
modifier par mégarde deux jeux de données divergents. Pour rester sur l'ancien
emplacement sans transfert, lancer explicitement
`python scripts/lancer-local.py --paquet ./paquet-autonome`.

Les migrations s'appliquent au démarrage. Lorsqu'une mise à jour du code exige
une migration, une copie de la base SQLite est créée d'abord dans
`sauvegardes-migrations/`. Le lanceur refuse aussi l'ouverture simultanée du
même paquet dans deux instances. Ces copies techniques ne remplacent pas une
sauvegarde complète de la base **et** des médias, prévue pour #L4.

Après la première connexion, créer une classe, ajouter une trace avec photo,
générer son carnet PDF et fermer la fenêtre. Relancer ensuite la même commande
et vérifier que l'école, la trace et le PDF sont toujours disponibles. Si le
moteur Web n'offre pas le téléchargement attendu, relever précisément le
comportement avant de considérer cette vérification acquise.

Ce jalon est un prototype à lancer depuis les sources, sans installateur :
le téléchargement des PDF dépend du moteur Web installé. Conserver ensemble
la base, les médias et la clé du paquet pour préparer une sauvegarde ou un
transfert ; `staticfiles/` peut être reconstruit au lancement depuis le code.
Une copie faite pendant que l'application tourne peut être incohérente.
La distribution sous forme d'installateur reste un jalon ultérieur.

### Sauvegarde et restauration du paquet local (#L4)

Dans la fenêtre locale, la direction ouvre **Gérer l'école → Sauvegardes
locales**. « Télécharger une sauvegarde » produit un ZIP avec la base SQLite,
les médias et la clé du paquet. PyWebView ouvre une boîte d'enregistrement
selon le moteur Web installé. Le ZIP contient des données privées :
à conserver comme le paquet lui-même.

Pour restaurer, sélectionner ce ZIP dans la même page. Le contenu et la base
SQLite sont vérifiés avant toute modification. Fermer ensuite la fenêtre pour
appliquer la restauration, puis relancer Petits Pas. Le paquet remplacé est
conservé dans un dossier voisin dont le chemin est affiché dans le terminal.
Une restauration en attente bloque les nouvelles écritures. Les éventuels
fichiers `staticfiles/` sont reconstruits au démarrage ; les copies techniques
`sauvegardes-migrations/` restent dans le paquet remplacé. Il n'est pas
nécessaire de restaurer un compte ou un référentiel séparément.

## Site public

Le site de présentation est construit avec Hugo depuis le répertoire `site/` :

```sh
sh scripts/preparer-site.sh
python3 scripts/verifier-guide-pratique.py
hugo --source site --minify
```

Hugo rend directement les contenus Markdown et Org-mode. Seuls les documents
explicitement placés dans `site/content/` sont publiés. Le contrôle préalable
vérifie les métadonnées des fiches pratiques, leurs liens internes et la
cohérence entre les captures utilisées et les scénarios fictifs déclarés.

## Licence

Le code de Petits Pas est distribué sous licence
[GNU Affero General Public License, version 3 ou ultérieure](LICENSE)
(`AGPL-3.0-or-later`). Cette licence autorise notamment l'usage, l'étude, la
modification, la redistribution et l'auto-hébergement du logiciel.

La politique applicable à la documentation, aux illustrations et aux données
est détaillée dans [CONTENUS-ET-LICENCES.md](CONTENUS-ET-LICENCES.md).
