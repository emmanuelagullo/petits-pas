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

### Prototype de fenêtre locale (#L1)

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
python scripts/lancer-local.py --creer-ecole "Mon école" --commune "Ma commune"
python scripts/lancer-local.py
# Ou, pour un autre emplacement :
python scripts/lancer-local.py --paquet /chemin/vers/mon-paquet
```

La commande `--creer-ecole` utilise la création d'école existante, charge
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
port libre. Fermer la fenêtre arrête le serveur. Par défaut, il crée
`./paquet-autonome/` à la racine du projet, avec `carnet.sqlite3`, `media/` et
`secret-key` ; ce répertoire est exclu de Git. Le chemin se règle aussi par
`PETITS_PAS_PAQUET_AUTONOME` (l'option `--paquet` a priorité). Un chemin
relatif est interprété depuis le répertoire de lancement. Les migrations
s'appliquent automatiquement à la base de ce paquet. Les anciennes données
de développement à la racine du dépôt ne sont pas importées ; aucun compte
ni jeu de démonstration n'est créé au lancement ordinaire. Le courrier est
désactivé.

Après la première connexion, créer une classe, ajouter une trace avec photo,
générer son carnet PDF et fermer la fenêtre. Relancer ensuite la même commande
et vérifier que l'école, la trace et le PDF sont toujours disponibles. Si le
moteur Web n'offre pas le téléchargement attendu, relever précisément le
comportement avant de considérer cette vérification acquise.

Ce jalon est un prototype à lancer depuis les sources, sans installateur :
le téléchargement des PDF dépend du moteur Web installé. Conserver ensemble
les trois éléments du paquet pour préparer une sauvegarde ou un transfert ;
une copie faite pendant que l'application tourne peut être incohérente.
Les jalons suivants traiteront la sauvegarde, le premier compte et la
distribution.

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
