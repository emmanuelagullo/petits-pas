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

## Captures de démonstration

Les captures fonctionnelles ne sont pas versionnées dans Git. Le pipeline
les génère depuis le jeu de données factices stable, avec une version de
navigateur, une taille de fenêtre et des dates fixées. Le job
`captures-demonstration` les transmet comme artefacts aux constructions Hugo,
qui les publient sous `captures/`.

Les ressources graphiques permanentes et leurs informations de licence peuvent
en revanche être versionnées dans `static/`.

Les paramètres publics partagés par le site et la démonstration Render sont
centralisés dans `data/demonstration.yaml`. Toute modification de ce fichier
affecte également `start-render.sh` et déclenche donc les contrôles de
l'application.

## Construction locale

```sh
hugo --source site --minify
```

Le résultat est écrit dans `site/public/`, répertoire ignoré par Git.

## Construction en CI

Les jobs `site-public` et `pages` héritent de la même définition Hugo dans
`.gitlab-ci.yml`. L'image est référencée par son digest immuable et fournit
actuellement Hugo Extended 0.140.2. Une mise à niveau de Hugo doit donc être une
modification explicite et validée, et non un effet de bord du tag `latest`.

La construction en CI utilise `--panicOnWarning` : tout avertissement Hugo fait
échouer le job. Les jobs Hugo désactivent aussi le cache Python global, dont ils
n'ont pas besoin.
