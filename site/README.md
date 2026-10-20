# Site public de Petits Pas

Ce répertoire contient le site Hugo publié par GitLab Pages.

## Contenus

Les pages peuvent être écrites en Markdown ou directement en Org-mode. Seuls
les fichiers sélectionnés dans `content/` deviennent publics : les documents
de travail placés ailleurs dans le dépôt ne sont jamais incorporés
implicitement.

Le rendu Org natif de Hugo est réservé à un sous-ensemble volontairement
simple : titres, paragraphes, listes, liens, tableaux, blocs de code et images.
Un document nécessitant les fonctions avancées d'Org devra disposer d'une
étape d'export explicite et testée.

Les quatre documents de conception des autorisations restent édités à la
racine du dépôt. `scripts/preparer-site.sh` copie exclusivement cette liste
blanche, avec des noms d'URL stables, dans
`content/conception/documents/`. Ce répertoire généré est ignoré par Git : les
originaux sont les seules sources à modifier.

## Captures de démonstration

Les captures fonctionnelles ne sont pas versionnées dans Git. Le pipeline
les génère depuis le jeu de données factices stable, avec une version de
navigateur, une taille de fenêtre et des dates fixées. Le job
`captures-demonstration` les transmet comme artefacts aux constructions Hugo,
qui les publient sous `captures/`.

Chaque connexion ferme le contexte navigateur précédent et ouvre un contexte
neuf, avec les mêmes paramètres d'affichage. Le script vérifie le nom complet
du personnage dans le menu avant de poursuivre : des réponses tardives d'un
ancien profil ne peuvent pas réinstaller ses cookies dans le nouveau contexte.

Les deux captures du mode autonome utilisent le même jeu fictif que le mode
hébergé. La CI termine le serveur de démonstration puis relance Django sur
`127.0.0.1` avec `CARNET_MODE_LOCAL=oui` pour montrer le vrai bouton de
sauvegarde et son écran, avant de construire le site.

Le démarrage peut inclure migrations et génération du jeu riche. Le script de
capture attend donc jusqu'à deux minutes que `/health/` réponde, afin de ne pas
confondre la variabilité d'un runner CI avec un échec applicatif.

Les ressources graphiques permanentes et leurs informations de licence peuvent
en revanche être versionnées dans `static/`.

Les scénarios documentaires, leurs chemins de sortie et les éventuels cadrages
ciblés sont déclarés dans `data/demonstration.yaml`. Trois parcours
représentatifs possèdent également une variante mobile de 390 × 844 pixels.
Avant chaque capture, Playwright contrôle la présence d'un contenu principal,
d'un titre de page et d'un unique `h1`, ainsi que l'absence de débordement
horizontal.

Le contrôle final refuse une capture manquante ou non déclarée, un format ou
des dimensions inattendus, un fichier de plus de 2 Mio ou un ensemble dépassant
12 Mio. Ces bornes empêchent une modification d'interface d'alourdir
silencieusement le site public ; elles doivent être réévaluées explicitement si
un nouveau besoin documentaire le justifie.

Les paramètres publics partagés par le site et la démonstration Render sont
centralisés dans `data/demonstration.yaml`. Toute modification de ce fichier
affecte également `start-render.sh` et déclenche donc les contrôles de
l'application.

## Construction locale

```sh
sh scripts/preparer-site.sh
hugo --source site --minify
```

La même préparation est nécessaire avant `hugo server` dans un clone neuf et
après chaque modification de l'un des quatre documents Org sources.

Le résultat est écrit dans `site/public/`, répertoire ignoré par Git.

## Construction en CI

Les jobs `site-public` et `pages` héritent de la même définition Hugo dans
`.gitlab-ci.yml`. L'image est référencée par son digest immuable et fournit
actuellement Hugo Extended 0.140.2. Une mise à niveau de Hugo doit donc être une
modification explicite et validée, et non un effet de bord du tag `latest`.

La construction en CI utilise `--panicOnWarning` : tout avertissement Hugo fait
échouer le job. Les jobs Hugo désactivent aussi le cache Python global, dont ils
n'ont pas besoin.

## Contenus cycle 1

`scripts/preparer-site.sh` publie aussi une liste explicite de YAML, registre,
notices et illustrations dans `static/referentiels/cycle1/`, ignoré par Git.
Modifier uniquement les originaux sous `referentiel/` ; la page publique
`content/referentiels/cycle1.md` les présente et propose un parcours d’essai.
L’édition Chat d’école, sa notice et son registre sont copiés de la même façon
dans `static/referentiels/chatdecole/`, depuis `referentiel/chatdecole/`.

## Parcours de démarrage (#SP1–2)

Les entrées principales partent des intentions : Démarrer, Essayer, Guide
pratique, Le projet, Contribuer. Institutions et hébergement et Protéger les
données sont accessibles depuis les parcours et le pied de page. Les anciennes
adresses restent conservées. Le shortcode `parcours` factorise les encadrés :
le titre explicite accompagne toujours la couleur et le symbole décoratif.

Distinguer le service de l’école de l’utilisation sur cet appareil ; cette
dernière permet plusieurs comptes, dans le navigateur ou le programme. Ne pas
confondre le code livré et les fonctions accessibles dans chaque publication.
La version affichée dans l’application et le catalogue des téléchargements
permettent de vérifier les fonctions disponibles.

Les comptes fictifs sont lus dans `site/data/demonstration.yaml` par le partial
`acces-demonstration.html`. Le shortcode `parcours` peut les afficher après
ses actions avec `comptes="oui"`, sans imbriquer un shortcode HTML dans son
contenu Markdown. Leur présentation est commune aux deux espaces d’essai.

## École fictive commune (#SP4)

Avant une construction locale complète du site, avec les dépendances Python :

```sh
python3 scripts/construire-ecole-fictive.py --destination site/static/essais/ecole-fictive.zip
```

Le script utilise une base temporaire et le même scénario que Render ; il ne
lit jamais la base du développeur. Le job de captures transmet le ZIP et sa
notice à Hugo, avec les captures. Ces fichiers générés sont ignorés par Git.
La page Essayer distingue les versions publiées des nouvelles fonctions locales.

## Versions proposées au téléchargement (#SP6)

`site/data/publications.yaml` conserve les dernières versions publiées connues.
Le job de captures lit les releases GitHub publiques avec
`scripts/preparer-publications-site.py` et transmet le catalogue généré aux
constructions Hugo. Les artefacts CI, brouillons et téléchargements absents
restent exclus. Une lecture indisponible conserve le catalogue connu ;
la date affichée précise l’observation. Après une release GitHub, relancer
les captures et la construction du site pour actualiser la liste. La PWA
garde son lien stable ; sa version et ses notes se lisent dans son aide.

## Notes de toutes les versions

`scripts/preparer-site.sh` extrait les rubriques numérotées de `CHANGELOG.org`
dans `content/notes-versions/*.org` (fichiers générés ignorés par Git).
Le journal reste l’unique source ; la rubrique À venir n’est pas publiée.
Les URL, par exemple `notes-versions/0.9/`, restent disponibles même si cette
étape n’a pas donné lieu à une release. Le catalogue de téléchargements continue
à ne proposer que les fichiers des releases publiques effectivement observées.
Après une release, actualiser aussi le catalogue conservé dans
`site/data/publications.yaml` à partir des fichiers publics, afin que les
constructions sans accès à l’API restent à jour.

## Thème commun et vérification (#SOC)

Avant toute construction (clone neuf compris) :

```sh
git submodule update --init site/theme-communs
```

Le gitlink épingle un commit public de Pas communs, utilisé uniquement pour
le thème Hugo. Lire `site/theme-communs/HUGO.md`. Ne pas utiliser `--remote`
en CI. Aucun changement de wheel Python ou de déploiement applicatif.
La CI initialise le sous-module dans les jobs Hugo ; les contenus et artefacts
métier continuent d’être préparés par les jobs habituels.

Menus : `site/hugo.toml`. Identité : `site/static/css/identite.css` et paramètre
`themeColor`. Accueil, contenus, comptes fictifs et shortcodes métier restent
locaux. Les layouts génériques, guide, navigation, encadrés et CSS viennent du
thème : ne pas en réintroduire une copie locale.

Après la préparation et la construction Hugo :

```sh
python3 site/theme-communs/hugo/verifier-site.py --sortie site/public --base-url https://example.invalid/produit/
```

Utiliser la même URL de base pour Hugo et le contrôle. Tester aussi la racine
et le préfixe public. Le contrôle attend les captures et fichiers d’essai du
produit lorsqu’ils sont référencés. Il ne remplace pas la revue clavier et
mobile/ordinateur. Pour une évolution commune : publier d’abord le commit du
socle sur GitLab Inria, puis avancer les sous-modules applicatifs, construire
et publier les sites. Le miroir GitHub conserve son rôle de miroir ; il n’est
pas utilisé pour récupérer le thème. Leurs URL restent inchangées.

Le sous-module utilise l’URL HTTPS absolue de GitLab Inria déclarée dans
`.gitmodules`. Cette déclaration fait foi pour la récupération du thème ;
l’ancienne mention du miroir GitHub dans le contrat du commit importé est
historique. Le commit adopté est celui effectivement publié sur Inria :
`5d64e2487939093bd6378a8a1611da95d93830ca`. Aucune reproduction de SHA avec
une commande spéciale `git am` n’est nécessaire.
