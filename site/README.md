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
