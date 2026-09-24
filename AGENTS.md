# Consignes pour les agents IA

Ce fichier s'applique à l'ensemble du dépôt Petits Pas. Lire d'abord
`README.md` et `CONTRIBUTING.md`, puis la documentation du domaine modifié.

## Repères

- Application Django / HTMX : `carnet/`, `comptes/`, `suivi/`, `referentiel/` ;
  point d'entrée `manage.py`.
- Site public Hugo : `site/` ; sa construction est décrite dans `README.md`.
- Pour comprendre les parcours réellement proposés, partir de
  `site/content/guide/` (fiches par intention et par rôle). Pour une vue
  accessible des fonctions et de leurs limites, consulter `site/content/roles/`.
  `site/content/guide/inventaire.md` recense la disponibilité des tâches :
  distinguer une fonction accessible d'une fonction seulement envisagée.
- Déploiement et atelier : `DEPLOIEMENT.org`, `ATELIER-PEDAGOGIQUE.org`,
  `REPRODUCTIBILITE.org`.
- Identités et autorisations : `POLITIQUE-AUTORISATION.org`,
  `MODELE-IDENTITES-ET-AFFECTATIONS.org`, `MATRICE-AUTORISATIONS.org` et
  `PLAN-IMPLEMENTATION-AUTORISATIONS.org`.
  `site/content/conception/_index.md` présente leur portée et leur chronologie :
  le code et les tests décrivent l'état effectivement implémenté.

## Travail dans le dépôt

- Préserver les parcours existants et vérifier les droits d'accès quand une
  modification touche aux comptes, classes, élèves, observations ou médias.
- N'utiliser que des données fictives dans les tests, captures, exemples et
  environnements de démonstration. Ne jamais ajouter de données personnelles,
  photographies d'enfants ou secrets au dépôt.
- Garder les textes destinés aux équipes pédagogiques compréhensibles et en
  français. Si un parcours change, mettre à jour la fiche du guide et, si
  nécessaire, l'inventaire, la présentation des rôles ou la page DSI.
- Pour modifier le site, lire `site/README.md` : les quatre documents de
  conception publiés sont copiés depuis la racine par `scripts/preparer-site.sh` ;
  ne pas éditer leurs copies générées. Les captures de démonstration sont
  générées depuis `site/data/demonstration.yaml` et ne sont pas versionnées.
- Limiter chaque modification au besoin demandé ; éviter les refontes
  incidentes. Suivre les conventions des fichiers voisins.

## Vérifications

Exécuter les vérifications pertinentes pour les fichiers modifiés. Les commandes
de référence sont dans `CONTRIBUTING.md` : tests Django, contrôle des migrations,
syntaxe des scripts shell, construction Hugo et `git diff --check`. Signaler
explicitement les vérifications non exécutées et leur raison.
