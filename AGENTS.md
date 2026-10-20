# Consignes pour les agents IA

## Écosystème, dépôts et responsabilités

Ces dépôts forment un même écosystème, avec trois responsabilités distinctes :

| Dépôt | Responsabilité | Référence Inria | Miroir GitHub |
| --- | --- | --- | --- |
| `pas-communs` | Socle et architecture techniques communs | <https://gitlab.inria.fr/pas-communs/pas-communs> | <https://github.com/emmanuelagullo/pas-communs> |
| `petits-pas` | Application métier : carnets de suivi en maternelle | <https://gitlab.inria.fr/petits-pas/petits-pas> | <https://github.com/emmanuelagullo/petits-pas> |
| `pas-a-pas-accompagnement` | Application métier : accueil et accompagnement social, notamment CHRS | <https://gitlab.inria.fr/pas-a-pas-accompagnement/pas-a-pas-accompagnement> | <https://github.com/emmanuelagullo/pas-a-pas-accompagnement> |

Inria est la référence du code ; GitHub est le miroir utilisé notamment pour
les constructions Windows/Linux et la publication des wheels et programmes.
Examiner le main public récent avant de préparer un patch. Les miroirs d'un
même dépôt doivent recevoir les mêmes commits et tags ; les versions des trois
dépôts restent indépendantes.

Les deux applications importent `pas_communs`, jamais le code de l'autre
application. Le socle est une bibliothèque embarquée, pas un service central.
Les mécanismes techniques partagés y résident : paquets et sauvegardes,
primitives d'authentification, exécution et construction locales, installateur
Windows, ressources navigateur, contrats serveur, recettes CI, intégrité des
publications et moteurs PDF. Se fier aux API réellement présentes et à leurs
contrats, sans supposer que toute l'infrastructure est déjà extraite.
Les modèles et migrations métier, rôles, permissions, parcours et contenus
restent propres aux applications. Comptes, bases, médias, secrets et espaces
navigateur sont séparés ; une primitive commune ne crée ni SSO ni équivalence
entre une école et un CHRS.

Les sites Hugo restent dans `site/` de chaque application. Les quatre dépôts
auxiliaires de publication ont les références Inria suivantes :

| Produit | Racine du domaine : redirection | Application navigateur : inclusion CI |
| --- | --- | --- |
| Petits Pas | <https://gitlab.inria.fr/petits-pas/petits-pas.gitlabpages.inria.fr> | <https://gitlab.inria.fr/petits-pas/petits-pas-pwa> |
| Pas à Pas | <https://gitlab.inria.fr/pas-a-pas-accompagnement/pas-a-pas-accompagnement.gitlabpages.inria.fr> | <https://gitlab.inria.fr/pas-a-pas-accompagnement/pas-a-pas-accompagnement-pwa> |

Ces auxiliaires ne contiennent ni second exemplaire de l'application, ni
bibliothèque métier, ni fork du socle. Aucun miroir GitHub de ces auxiliaires
n'est déclaré ici : ne pas en inventer un. Le préparateur PWA, les constructeurs,
les manifestes et les sources des sites se modifient dans le dépôt applicatif.

## Coévolution et séparation des préoccupations

- Pour une évolution strictement métier, intervenir dans l'application concernée.
  Dès qu'une évolution dépasse cette couche, examiner aussi le socle, l'autre
  application et les dépôts de publication affectés. Lire leurs AGENTS.md et
  contrats ; expliciter les impacts et les adaptations nécessaires.
- Factoriser ce qui est factorisable et harmoniser ce qui est harmonisable.
  Rechercher un mécanisme existant avant d'en recopier un. Extraire les mécanismes
  techniques communs dans pas-communs avec des paramètres ou façades propres aux
  produits ; harmoniser les conventions et recettes qui peuvent rester dans
  leurs dépôts. Justifier l'abstraction par les usages des deux applications,
  sans imposer un modèle métier commun ni une abstraction spéculative.
- Préparer ensemble les changements du socle et les adaptations des consommateurs.
  Vérifier les deux usages touchés, leurs compatibilités et leurs profils
  serveur/bureau/PWA pertinents. La CI du socle ne qualifie pas à elle seule
  les applications ; préserver sauvegardes historiques, données et identités.
- La version réellement adoptée est fixée par requirements-communs.txt (URL du
  wheel et SHA-256). Les mentions de versions dans les anciens jalons décrivent
  leur historique. Pour du code ou des ressources du socle, publier une nouvelle
  version immuable avant de pousser les consommateurs qui la requièrent. Une
  modification de documentation seule ne nécessite pas de nouveau wheel.
- Livrer les patches par dépôt avec l'ordre d'application, de publication et de
  vérification. Maintenir cette carte et les AGENTS.md affectés cohérents. Annoncer
  à l'avance tout changement de profils d'installation ou de commandes de
  déploiement pour permettre la préparation des instances existantes.
- Dans les deux applications, les tags numériques qualifiés déclenchent les
  releases GitHub ; seuls les tags sans suffixe publient automatiquement la PWA,
  à partir des artefacts validés sans
  reconstruction ; la reprise manuelle reste disponible. Sur main, la publication
  PWA reste manuelle. Les déploiements serveur gardent leur procédure séparée
  et ne sont pas modifiés implicitement
  par une extraction du socle ou une publication de programme/PWA.

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
- Normalisation, compression, variantes PDF et futurs quotas de médias : lire
  =POLITIQUE-MEDIAS.org=, puis =RECETTE-MEDIAS.org= pour le protocole et la
  référence mesurée. Le profil ordinaire reste simple et les quotas sont
  désactivés par défaut. Le traitement dans le navigateur est une optimisation ;
  la validation du serveur reste obligatoire. Ne jamais recomprimer
  silencieusement les médias existants après un changement de politique.
- Évolution des référentiels : `AUDIT-REFERENTIELS.org` fixe le périmètre et
  les jalons ; `MODELE-REFERENTIELS.org` les règles retenues,
  `DIAGNOSTIC-REFERENTIELS.org` la reprise et la lecture annuelle,
  `IMPORT-SOURCES-REFERENTIELS.org` l'import versionné et
  `CHOIX-BASES-REFERENTIELS.org` les autorisations et défauts annuels,
  `ADAPTATIONS-REFERENTIELS.org` les libellés et masquages annuels,
  `AJOUTS-REFERENTIELS.org` les identités et reprises des ajouts locaux,
  `CORRESPONDANCES-REFERENTIELS.org` les liens explicites sans transfert d’acquis,
  `MISES-A-JOUR-REFERENTIELS.org` l’aperçu et l’adoption des versions sources,
  `GARDE-FOUS-REFERENTIELS.org` les permissions annuelles, niveaux
  d’avertissement et confirmations renforcées. Les règles communes sont dans
  `suivi/services/garde_fous_referentiels.py` ; les confirmations web dans
  `suivi/confirmations_referentiels.py`. Leur lecture
  commune est dans `suivi/adaptations_referentiels.py` ; les écritures contrôlées
  sont dans `suivi/services/adaptations_referentiels.py`.
  Distinguer les services préparés des fonctions accessibles ; importer,
  autoriser, proposer par défaut et adopter sont des actions distinctes.
- Sources du référentiel et des icônes : `referentiel/README.md`, les fichiers
  YAML et `referentiel/static/`. `suivi/referentiels.py` partage la lecture et
  l'ordre des compétences entre saisies, réglages et carnets ; réutiliser cette
  logique plutôt que créer des tris concurrents.

- Application navigateur : `pwa/README.md` décrit l'architecture et les parcours ;
  `pwa/QUALIFICATION.md` consigne les essais et leurs limites. Les commandes
  `scripts/verifier-pwa.cjs` et `scripts/qualifier-pwa.cjs` n'emploient que des
  profils fictifs. Ne jamais distribuer un bundle construit avec `--test`.
  `pwa/PUBLICATION.md` décrit la publication du bundle validé vers
  un projet Pages dédié, à la racine ou sous `/petits-pas-pwa/` ; conserver
  son adresse stable et le site Hugo. La portée du Service Worker et les
  données internes sont propres au chemin, sans isolation de sécurité entre
  projets partageant une origine.
  Les jobs `pwa-prototype` et `pwa-qualification` sont automatiques et leurs
  échecs font échouer la CI ; la publication est automatique sur tag qualifié
  et reste manuelle sur main.
  `pwa/MEDIA-OPFS.md` décrit #PWA11 : lectures WORKERFS sur blobs immuables,
  écritures transitoires MEMFS. `pwa/TRANSFERTS-OPFS.md` décrit #PWA12 :
  ZIP progressifs et décompression par fichier vers des blobs immuables. `lazy_media.js` dépend
  des nœuds Emscripten du runtime épinglé ; requalifier avant de le changer.
  Ne pas écrire en place dans les blobs confirmés ni contourner les vues médias.
  `scripts/publication.py` partage identité, notes et manifestes de candidats.
  Les notes restent dans `CHANGELOG.org` : À venir sur main, rubrique du tag
  pour une version numérotée. Les programmes se publient automatiquement sur
  GitHub après qualification du tag, avec reprise depuis Actions ou en CLI ;
  la PWA sur GitLab Pages, depuis le même pipeline que ses
  contrôles réussis. Ne pas confondre tag, construction et publication ni
  mettre les paramètres d’exploitation d’une école dans un manifeste.
  Le catalogue Hugo ne lit que les releases publiques, pas les artefacts CI.
  `pwa/ESSAIS-APPAREILS.md` recueille les retours terrain sans bloquer les
  évolutions. `pwa/AUDIT-SITE-PUBLICATIONS.md` prépare le chantier Hugo.
  Le suivi du ZIP préparé est commun à PWA/autonome dans `suivi/paquet_local.py` ;
  ne pas le présenter comme une preuve de copie conservée.
  Lire `pwa/PRODUCTION.md` pour le périmètre de production et la maintenance.
  Conserver les sauvegardes communes dans `suivi/paquet_local.py` et distinguer
  les bancs automatisés de la qualification sur appareils d'école.

## Socle partagé (#SOC2)

Lire `SOCLE-COMMUN.md`. Le moteur ZIP/SQLite vient de `pas_communs.paquets` ;
conserver la façade `suivi.paquet_local`, ses confirmations et les droits métier.
Ne pas réintroduire une copie du moteur. Toute évolution de la dépendance exige
une version publiée et une empreinte dans `requirements-communs.txt`, avec les
essais serveur/bureau/PWA pertinents. Préserver les anciens ZIP et plafonds OPFS.

## Travail dans le dépôt

- Export d'école serveur → local : lire `EXPORT-ECOLE.org` et
  `suivi/exports_ecole.py`. Export de classe : `EXPORT-CLASSE.org`,
  `suivi/exports_classe.py` et `suivi/export_projection.py` ; conserver les
  autorisations indépendantes et les médias OPFS progressifs, filtrer aussi
  les instantanés JSON annuels. Toute nouvelle table métier exige une décision
  explicite dans la projection. Ne pas copier les secrets serveur, étendre
  les droits pédagogiques par analogie, ni relever les plafonds PWA sans
  qualification. Le traitement est séparé des workers WSGI et le ZIP est privé.
  Import local → nouvelle école serveur : lire `IMPORT-ECOLE.org` et
  `suivi/imports_ecole.py`. Aucun remplacement, rapprochement de comptes ou
  reprise de capacités du ZIP ; remapper aussi les PK et chemins des JSON.
  Conserver la vérification sans écriture, l'empreinte confirmée et l'annulation
  SQL/fichiers. Toute nouvelle structure JSON exige une décision explicite.

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

- Utiliser l’identité de commit explicitement indiquée ; si elle n’est pas
  précisée, la demander avant de créer les commits.
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

## Contrats techniques hérités des jalons

#SOC3 : les mécanismes du lanceur et l’assemblage PyInstaller viennent de
`pas_communs.local` et `pas_communs.construction`. Conserver les chemins,
installateurs et callbacks métier Petits Pas ; tester arrêt et restauration.

#SOC4a : conserver les façades comptes.totp/validators/backends et les modèles
historiques. Le moteur TOTP ne consomme rien : persister les pas sous transaction
et conserver limites de tentatives, politiques et confirmations dans Petits Pas.
Tester aussi les attentes expirées, révoquées et les parcours de secours.

#SOC5a : les ressources JavaScript du socle sont copiées depuis le wheel dans
le bundle PWA. Garder les façades, noms historiques et états essai/aperçu.
Tester scripts Python, transport et banc Chromium. Ne pas remplacer les
transferts ou restaurations métier par les adaptateurs minimaux du CHRS.

#SOC6a : lire SERVEUR-SOCLE.md pour le nouveau profil volontaire. Ne pas changer
carnet.settings par défaut ni la configuration d'une instance. Garder confiance
HTTPS au proxy et confiance dans l'adresse cliente comme deux choix distincts.
Exécuter scripts/verifier-profil-serveur.py.

#SOC6b : la CI Django utilise la recette du wheel. Conserver les contrôles de
référentiels, médias, shell et le service PostgreSQL propres au produit.
Les façades scripts/publication.py et validate_bundle conservent leur contrat ;
les notes, contrôles d'origine/job/tag et décisions de publication restent ici.

#SOC7b : le rendu PDF natif est dans pas_communs.pdf (0.6.0), appelé par
les façades du produit. Les droits, contenu et templates restent ici. Tester
les vrais PDF, le téléchargement et les dépendances propres aux profils.
Ne pas importer WeasyPrint/Pango dans le navigateur ni remplacer les carnets
scolaires par le backend texte. Préserver le chargement autorisé des médias.

#SOC3b : le setup Windows utilise pas_communs.installateur_windows et la
configuration produit scripts/installateur-windows.json. Ne pas modifier
l’AppId historique, les chemins installés ou le raccourci lors de l’extraction.
Conserver le contrôle du journal et la promotion des octets validés.

#SOC6c — publications automatiques : un tag numérique qualifié déclenche
la release GitHub ; la PWA automatique exige un tag sans suffixe. Le workflow de publication GitHub utilise le code de
main et les artefacts du run terminé ; ignorer branches, PR, forks et échecs.
Conserver les vérifications des deux forges et la reprise manuelle. Les
déploiements serveur restent indépendants, sans changement de déclenchement.


#AUD : lire les contrats actualisés et la recette QUALIFICATION.md de pas-communs.
La version 0.8.0 est publiée et adoptée ; préserver son tag et ses octets.
Une modification documentaire seule ne demande pas de nouveau wheel. Les
consommateurs peuvent conserver des versions différentes, explicitement épinglées.
Préserver les noms ZIP historiques portables ; refuser les alias Windows à
l'export comme à l'import sans renommer les données. Le runtime Pyodide est
sélectionné explicitement dans les constructeurs ; les politiques de promotion
et de déploiement restent applicatives. Qualifier les octets du wheel et les
deux consommateurs ; aucune installation pip n'est implicite dans cette recette.

#AUD — TOTP : pas de verrou de ligne supposé sous SQLite. Conserver le
compare-et-échange lié à la clé/confirmation et le refus sur erreur de stockage.
Tester scripts/qualifier-totp.py (SQLite fichier), ainsi que les tests ordinaires
sous PostgreSQL ; ne pas déplacer les modèles ou changer les sessions pour
cette correction de consommation.


Compléments AUD : conserver les deux témoins historiques de scripts/fixtures ;
le ZIP 0.10 représentatif reste fictif et immuable. Exécuter
scripts/test_archive_historique.py via unittest sur les profils concernés.
Python du constructeur PWA >=3.12 et Python embarqué Pyodide sont distincts.
La politique du canal stable est décrite dans pwa/PUBLICATION.md.

Politique PWA adoptée : seuls les tags sans suffixe publient automatiquement
à l’adresse habituelle. Les préversions sont construites et testées, mais refusées
par le préparateur Pages. La publication de main reste manuelle.

#SOC — copies : adoption candidate de 0.9.0, à pousser après publication du wheel.
Lire SAUVEGARDES.md dans pas-communs. Les ZIP restent privés, complets et propres
au produit ; ne pas les transformer en démonstration distribuable. Conserver les
sessions de la source et vider seulement celles de la préparation restaurée.

#SOC — sites : lire site/README.md et site/theme-communs/HUGO.md. Initialiser
le sous-module épinglé avant Hugo. Ne pas recopier les layouts/styles du thème.
Conserver contenus, démonstration, URL et paramètres de couleur propres au produit.
