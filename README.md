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

## Site public

Le site de présentation est construit avec Hugo depuis le répertoire `site/` :

```sh
hugo --source site --minify
```

Hugo rend directement les contenus Markdown et Org-mode. Seuls les documents
explicitement placés dans `site/content/` sont publiés.

## Licence

Le code de Petits Pas est distribué sous licence
[GNU Affero General Public License, version 3 ou ultérieure](LICENSE)
(`AGPL-3.0-or-later`). Cette licence autorise notamment l'usage, l'étude, la
modification, la redistribution et l'auto-hébergement du logiciel.

La politique applicable à la documentation, aux illustrations et aux données
est détaillée dans [CONTENUS-ET-LICENCES.md](CONTENUS-ET-LICENCES.md).
