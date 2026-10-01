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
- Images, phrases proposées et choix école/classe : partir de
  `site/content/guide/carnets/personnaliser-presentation.md` pour les usages,
  puis de `AUDIT-TRACES-PARTAGEES.org` pour le bilan et les limites du chantier.
  Les règles d'héritage effectivement appliquées sont dans
  `suivi/presentation.py` ; les droits et l'enregistrement des choix sont dans
  `suivi/services/presentation.py`, les contraintes dans `suivi/models.py`,
  et les scénarios vérifiés dans `suivi/tests_presentation.py`.
  Ces règles concernent les images et les phrases proposées : ne pas les
  étendre automatiquement aux restrictions de stockage ou à l'évolution des
  référentiels. Distinguer un choix proposé par défaut d'une interdiction.
- Évolution des référentiels : `AUDIT-REFERENTIELS.org` fixe le périmètre et
  les jalons ; `MODELE-REFERENTIELS.org` les règles retenues,
  `DIAGNOSTIC-REFERENTIELS.org` la reprise et la lecture annuelle,
  `IMPORT-SOURCES-REFERENTIELS.org` l'import versionné et
  `CHOIX-BASES-REFERENTIELS.org` les autorisations et défauts annuels,
  `ADAPTATIONS-REFERENTIELS.org` les libellés et masquages annuels,
  `AJOUTS-REFERENTIELS.org` les identités et reprises des ajouts locaux,
  `CORRESPONDANCES-REFERENTIELS.org` les liens explicites sans transfert d’acquis,
  `MISES-A-JOUR-REFERENTIELS.org` l’aperçu et l’adoption des versions sources. Leur lecture
  commune est dans `suivi/adaptations_referentiels.py` ; les écritures contrôlées
  sont dans `suivi/services/adaptations_referentiels.py`.
  Distinguer les services préparés des fonctions accessibles ; importer,
  autoriser, proposer par défaut et adopter sont des actions distinctes.
- Sources du référentiel et des icônes : `referentiel/README.md`, les fichiers
  YAML et `referentiel/static/`. `suivi/referentiels.py` partage la lecture et
  l'ordre des compétences entre saisies, réglages et carnets ; réutiliser cette
  logique plutôt que créer des tris concurrents.

## Travail dans le dépôt

- Préserver les parcours existants et vérifier les droits d'accès quand une
  modification touche aux comptes, classes, élèves, observations ou médias.
- N'utiliser que des données fictives dans les tests, captures, exemples et
  environnements de démonstration. Ne jamais ajouter de données personnelles,
  photographies d'enfants ou secrets au dépôt.
- Privilégier des parcours simples pour les enseignants : partir de la tâche
  à accomplir, limiter les étapes et rendre explicites les conséquences d'une
  action, notamment lorsqu'elle concerne plusieurs enfants.
- Garder les textes en français, avec des mots courants et des exemples
  concrets ; éviter le jargon technique dans les écrans et le Guide pratique.
  Les libellés du guide doivent correspondre aux boutons réellement proposés.
  Placer les explications longues dans une aide dépliable, fermée par défaut,
  lorsque cela facilite la saisie. Ne pas réserver une information nécessaire
  au seul survol de la souris : elle doit rester accessible au clavier et sur
  un écran tactile.
- Mettre à jour le Guide pratique lorsqu'une fonction devient effectivement
  accessible, et lorsqu'un parcours, un droit ou une limite change. Vérifier
  aussi l'inventaire, les fiches liées, les rôles et, si nécessaire, la page DSI.
  Ne pas présenter une fonction seulement envisagée comme déjà disponible.
- Pour modifier le site, lire `site/README.md` : les quatre documents de
  conception publiés sont copiés depuis la racine par `scripts/preparer-site.sh` ;
  ne pas éditer leurs copies générées. Les captures de démonstration sont
  générées depuis `site/data/demonstration.yaml` et ne sont pas versionnées.
- Limiter chaque modification au besoin demandé ; éviter les refontes
  incidentes. Suivre les conventions des fichiers voisins.

## Commits et livraisons

- Rédiger le sujet des commits en français et reprendre le repère du chantier
  lorsqu'il existe. Pour la phase 5 :
  `Phase 5: #C6a clarifier le message de connexion et le diagnostic d'envoi`.
  Pour le mode autonome : `#L5 : publier les mêmes archives depuis un tag commun aux deux forges`.
  Conserver les suffixes des sous-étapes (`#C6b`, `#L6b`, etc.) plutôt que
  d'inventer un nouveau jalon à chaque correction. Sans repère de chantier,
  choisir un sujet français descriptif.
- Pour les contributions préparées par un agent, livrer un patch applicable
  avec `git am`, sur le `main` récent. Aucun `Signed-off-by` n'est
  nécessaire. Vérifier que le patch s'applique avant de le remettre.

## Vérifications

Exécuter les vérifications pertinentes pour les fichiers modifiés. Les commandes
de référence sont dans `CONTRIBUTING.md` : tests Django, contrôle des migrations,
syntaxe des scripts shell, construction Hugo et `git diff --check`. Signaler
explicitement les vérifications non exécutées et leur raison.
