# Audit de performance de Petits Pas — 5 octobre 2026

Base de départ : `main`, `3e8af5998d3b5c8673164173db385637c50e6b8a`.
Auteur des patchs : Emmanuel Agullo <emmanuel.agullo@inria.fr>.

## Bilan et priorités

L’ordre combine le coût démontré, la fréquence des parcours et la possibilité d’une correction limitée. Le PDF groupé domine les durées, mais demande un chantier distinct.

1. **Listes d’élèves : coût SQL proportionnel à l’effectif.** Sur 30 élèves et 417 compétences, la classe effectue 150 requêtes, la saisie collective 85, le formulaire de trace partagée 117 et la préparation des carnets 98. La scolarité courante est relue plusieurs fois par élève. Correction : préchargement explicite pour les listes de lecture, en conservant toutes les années pour identifier la plus récente. Aucun cache global des droits ou des scolarités.
2. **Grande équipe : recherche quadratique des remplaçants.** Avec 33 membres et 31 classes, 1 126 → 134 requêtes ; médiane locale 0,451 → 0,138 s. Réutilisation des affectations déjà chargées, en conservant exactement les critères d’état et de dates et les contrôles de gouvernance. Ce résultat est à traiter avant toute optimisation du volume HTML.
3. **Enregistrement d’une trace partagée : contrôles identiques par enfant.** Pour 30 enfants, 332 → 156 requêtes. La sélection vérifie toujours individuellement la classe, l’année, l’école et l’absence d’archivage. Les deux droits portant sur cette même classe sont contrôlés une fois ; les attributions, la personnalisation, les versions personnelles et les écritures restent individuelles.
4. **Carnet regroupé par année : une requête supplémentaire par acquisition.** Pour 20 observations initiales, 83 requêtes contre 62 sans regroupement. Les scolarités et les bilans étaient également relus pour chaque domaine. Correction : lectures communes au carnet, bilans chargés seulement pour le regroupement par bilan.
5. **Traces sans photo : contrôles de téléchargement inutiles par trace.** Passer de 1 à 10 traces fait passer leur écran de 80 à 116 requêtes. Correction : ne calculer le droit de télécharger un original que lorsqu’un fichier existe. Les contrôles existants restent appliqués aux photos. Les relations classe/école et origine des traces sont préchargées pour éviter leurs lectures par trace.
6. **Édition groupée PDF : coût séquentiel par élève et par contenu.** Pour 30 élèves : environ 13–15 s avec une trace par acquisition, 25 s avec dix traces. Le rendu WeasyPrint domine. Les patchs SQL ne rendent pas cette génération instantanée. Une file de travaux ou un changement de moteur constituerait un chantier distinct ; aucun n’est introduit ici.
7. **Grandes pages HTML : coût proportionnel au référentiel.** La liste de saisie individuelle atteint environ 365 ko avec 417 compétences ; la liste des compétences pour la saisie collective environ 407 ko. Les requêtes restent bornées quand on augmente les compétences, mais le rendu Django, le transfert et le travail du navigateur croissent. Pagination ou affichage progressif à discuter sur mesures navigateur ; pas de modification du parcours enseignant dans ces patchs.

## Protocole et interprétation

- Lecture de `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `site/README.md`, de l’inventaire du Guide pratique, des règles d’autorisation et annuelles concernées, puis du code et des tests.
- 185 mesures principales (37 parcours × 5 jeux), puis 20 mesures complémentaires (10 parcours × 2 jeux). Les compléments exercent un rectangle PNG synthétique de 640 × 480 pixels, 8 puis 33 membres, 6 puis 31 classes, les contributions et attributions partagées, la consultation adaptée et la vérification d’un ZIP avant restauration.
- Cinq jeux : 5 ou 30 élèves, 20 compétences fictives ou les 417 compétences Chat d’école, 20 observations initiales par élève, 1 ou 10 traces textuelles par acquisition. Une trace commune attribuée à toute la classe, un bilan par élève, trois rôles (responsable, contributeur, direction). Les données de personnes, productions et médias sont exclusivement fictives.
- Base SQLite temporaire et stockage local, paramètres d’exploitation neutralisés, `DEBUG=False`, mode local, courrier et anti-bruteforce désactivés. Migrations et collecte des statiques avant mesure. Une chauffe puis trois répétitions, médiane/minimum/maximum dans les JSON.
- Client de test Django : temps du traitement complet, middleware, autorisations, rendu du gabarit, session et consommation des réponses diffusées inclus. Aucun réseau HTTP, navigateur, JavaScript, mise en page écran ou latence d’hébergement dans ces temps. Les requêtes sont instrumentées par `CaptureQueriesContext` ; le rendu WeasyPrint est exécuté pour les PDF, sans simulation.
- Volumes : corps de réponse, en octets, sans compression HTTP. Les JSON détaillent les cinq motifs SQL les plus répétés. La somme des durées SQL affichées par Django est arrondie à la milliseconde par requête : elle ne mesure pas précisément les nombreuses petites lectures SQLite.
- Tous les parcours répondent en 200 ; les écritures complémentaires attendent leur redirection 302. Les écritures HTMX changent réellement les états fictifs ; trois bascules reviennent au même état. Les chauffes laissent une observation dans un autre état avant les mesures PDF ; les deux campagnes suivent le même ordre. Les écritures complémentaires sont annulées par transaction.
- Les écoles des cinq jeux coexistent dans la base temporaire : les sauvegardes portent sur le paquet complet, qui grossit au fil des scénarios, et sur 2 Mio de données binaires fictives peu compressibles. Le nombre de requêtes ne compte pas les appels SQLite directs du moteur de sauvegarde et de vérification.
- Les durées ne sont pas une promesse pour Render ou PostgreSQL. La charge de la machine n’est pas stabilisée et les mesures après correction peuvent être plus lentes sur des parcours dont le SQL n’a pas changé. Les gains démontrés sont les suppressions des lectures répétées, avec tests sur la croissance des données.

L’environnement mesuré est Python 3.12.14, Django 6.1.1, WeasyPrint 68.1 sous Linux, base SQLite ; ce n’est pas le Python 3.13 ni le PostgreSQL d’une instance d’école. La campagne finale des pages et le complément ont été rejoués après les derniers changements. Les PDF utilisent la passe précédente à trois répétitions : leur code n’a pas été modifié par les derniers ajustements des écrans de traces, de l’équipe et du service partagé.

## Render et navigateur

Les chiffres transmis au départ (1 307 → 55 requêtes ; local 1,39 → 0,14 s ; Render environ 30 → 2–3 s) concernent la correction précédente et un autre jeu d’essai. Ils ne sont pas intégrés comme mesures de cette campagne.

Une lecture indépendante de `/health/` sur Render a répondu en 200, 16 octets, avec 5,142 s jusqu’au premier octet et 5,144 s au total. Ce temps inclut le réseau et le proxy de l’environnement d’audit ; aucune décomposition interne serveur n’est disponible. Il ne permet pas d’attribuer la lenteur de Render à Django ni de mesurer le gain des nouveaux patchs. Aucun test de charge, reset ni modification de la démonstration publique.

Les temps du navigateur restent **non mesurés** : Chromium absent et téléchargement du moteur indisponible dans cet environnement. Les grands corps HTML démontrent un volume à traiter, pas un temps de rendu écran. Complément à relever sur une machine d’école : TTFB, fin de téléchargement, `DOMContentLoaded`, affichage utile, ressources statiques/médias, durée d’une recherche et d’un remplacement HTMX, cache froid puis chaud. Pour Render, utiliser les mêmes données fictives et le même commit, distinguer démarrage à froid et service chaud, et relever les temps applicatifs côté serveur.

## Reproduction

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python scripts/auditer-performance.py --pdf --sortie /tmp/performance.json
python scripts/auditer-performance.py --complements --sortie /tmp/performance-complements.json
```

Cette commande ne lit ni ne modifie la base de travail. Les paramètres `CARNET_*`, `DATABASE_URL`, `DJANGO_*`, `RENDER_*` et `PETITS_PAS_*` sont neutralisés avant l’initialisation Django. `AUDIT_RACINE` permet de comparer un autre checkout avec le même protocole. Les JSON détaillés et le tableau CSV accompagnent les patchs.

## Avant/après sur le gros jeu

30 élèves, 417 compétences, 20 observations initiales chacun, dix traces par acquisition plus une trace commune. Les temps sont des **millisecondes serveur locales instrumentées**, pas des temps navigateur. Le volume est celui de la réponse après correction, en Kio (1 024 octets).

| Parcours | SQL avant | SQL après | ms avant | ms après | Kio après |
| --- | ---: | ---: | ---: | ---: | ---: |
| accueil | 37 | 37 | 36.8 | 34.7 | 1.9 |
| classe | 150 | 61 | 123.4 | 90.0 | 12.2 |
| classe-tous | 90 | 61 | 95.1 | 94.6 | 12.2 |
| individuel | 59 | 59 | 150.4 | 147.2 | 357.8 |
| contribution | 48 | 48 | 82.9 | 79.1 | 136.6 |
| competences | 47 | 47 | 135.5 | 129.7 | 397.1 |
| collectif | 85 | 56 | 102.8 | 97.5 | 28.1 |
| grille | 47 | 47 | 59.4 | 61.3 | 9.1 |
| trace | 116 | 71 | 110.8 | 82.7 | 17.4 |
| traces-partagees | 53 | 53 | 69.6 | 70.3 | 2.6 |
| trace-partagee | 117 | 58 | 91.7 | 66.1 | 12.8 |
| referentiel | 45 | 45 | 41.2 | 40.4 | 5.6 |
| consulter | 41 | 41 | 46.2 | 40.9 | 143.1 |
| adaptations | 41 | 41 | 66.5 | 62.8 | 97.1 |
| presentation | 56 | 56 | 88.9 | 89.7 | 148.4 |
| ajouts | 49 | 49 | 45.2 | 46.0 | 4.7 |
| correspondances | 63 | 63 | 87.0 | 82.9 | 186.0 |
| permissions | 40 | 40 | 33.1 | 35.1 | 3.2 |
| carnet | 62 | 62 | 72.3 | 71.2 | 31.6 |
| carnet-tout | 62 | 62 | 105.7 | 103.0 | 207.7 |
| carnet-annuel | 83 | 63 | 77.9 | 70.4 | 31.7 |
| carnet-bilans | 63 | 63 | 73.1 | 70.4 | 31.7 |
| bilans | 48 | 48 | 39.1 | 37.9 | 3.6 |
| edition | 98 | 39 | 59.8 | 36.2 | 8.4 |
| gestion | 35 | 35 | 27.1 | 27.1 | 2.8 |
| equipe | 46 | 44 | 35.4 | 33.5 | 7.5 |
| annuaire | 36 | 36 | 30.3 | 30.0 | 9.2 |
| composition | 37 | 37 | 36.6 | 33.9 | 52.3 |
| parcours | 31 | 31 | 24.2 | 24.6 | 3.0 |
| referentiels-ecole | 40 | 40 | 36.3 | 33.6 | 7.2 |
| sauvegardes | 28 | 28 | 24.7 | 26.6 | 4.0 |
| htmx-individuel | 93 | 93 | 81.2 | 82.9 | 1.0 |
| htmx-collectif | 93 | 93 | 84.0 | 77.8 | 0.9 |
| zip-sauvegarde | 17 | 17 | 137.3 | 132.1 | 2741.3 |
| pdf | 71 | 71 | 822.6 | 1025.2 | 24.2 |
| pdf-grille | 49 | 49 | 422.5 | 598.6 | 15.3 |
| zip-pdf | 1499 | 1500 | 25347.0 | 28301.2 | 657.0 |
| trace-photo | 161 | 138 | 187.4 | 172.3 | 18.7 |
| equipe-large | 1126 | 134 | 451.1 | 138.1 | 190.0 |
| gestion-large | 35 | 35 | 31.4 | 34.2 | 10.0 |
| media-photo | 24 | 24 | 19.1 | 22.9 | 1.9 |
| original-photo | 27 | 27 | 22.7 | 25.9 | 1.9 |
| post-trace | 76 | 76 | 78.2 | 76.3 | 0.0 |
| post-partage | 332 | 156 | 230.8 | 98.4 | 0.0 |
| post-restauration | 18 | 18 | 35.9 | 33.7 | 0.0 |
| consulter-source | 41 | 41 | 44.4 | 43.0 | 143.1 |
| consulter-adapte | 46 | 46 | 56.7 | 54.9 | 143.1 |

Les réponses HTML ont le même contenu fonctionnel et le même volume dans ces scénarios. Les PDF/ZIP peuvent varier de quelques octets (métadonnées, dates et compression). Les POST complémentaires renvoient une redirection de corps vide ; leur coût mesure l’enregistrement ou la vérification, pas l’affichage de la page suivante. La génération du ZIP de PDF prend une requête de plus (préchargement commun de la liste d’élèves avant le POST) ; son coût reste dominé par le rendu, sans accélération démontrée.

## Croissance des données

| Jeu | Classe SQL avant → après | Collectif SQL avant → après | Édition SQL avant → après | Suivi individuel SQL avant → après | Carnet annuel SQL avant → après |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5e-20c-1t | 75 → 61 | 60 → 56 | 48 → 39 | 59 → 59 | 83 → 63 |
| 30e-20c-1t | 150 → 61 | 85 → 56 | 98 → 39 | 59 → 59 | 83 → 63 |
| 5e-417c-1t | 75 → 61 | 60 → 56 | 48 → 39 | 59 → 59 | 83 → 63 |
| 30e-417c-1t | 150 → 61 | 85 → 56 | 98 → 39 | 59 → 59 | 83 → 63 |
| 30e-417c-10t | 150 → 61 | 85 → 56 | 98 → 39 | 59 → 59 | 83 → 63 |

`e` = élèves, `c` = compétences, `t` = traces par acquisition. Les coûts SQL corrigés des listes restent stables avec l’effectif. Le suivi individuel et la liste de compétences restent bornés avec les compétences ; leurs volumes HTML et temps de rendu augmentent. Les carnets chargent les traces en groupe : multiplier leur nombre augmente les objets et le HTML/PDF, sans requête SQL par trace.

## Coûts restant ouverts et suite proposée

- **PDF de classe** : boucle séquentielle par élève, relecture et contrôles individuels du carnet, rendu WeasyPrint et ZIP en mémoire. C’est un coût réel, pas un N+1 entièrement éliminable par `select_related`. Mesurer d’abord le temps des contextes, du moteur PDF, des images et le pic mémoire avec de vraies tailles de médias synthétiques. Envisager ensuite une génération différée ; pas de parallélisation automatique des droits, du stockage ou des sessions ici.
- **Photos** : les contrôles d’accès au téléchargement sont encore individuels. L’écran avec onze photos passe de 161 à 138 requêtes. Les endpoints de miniature et original restent respectivement à 24 et 27 requêtes, avec un fichier PNG de 1 949 octets. Cette mesure ne qualifie pas le redimensionnement, les gros JPEG ni le stockage S3. Des médias nombreux coûtent autant de requêtes HTTP et de transferts au navigateur.
- **HTMX** : environ 1 ko de réponse mais 93 requêtes, indépendamment du nombre d’élèves/compétences. Le traitement vérifie les droits, le contexte annuel, modifie l’état, journalise et prépare un contexte de rendu. Le coût fixe justifie un prochain examen de la réponse partielle, pas un cache global des autorisations.
- **Équipe** : les allers-retours quadratiques disparaissent. La liste des options de remplacement reste quadratique en volume HTML avec beaucoup de responsables ; les contrôles de fin d’affectation sont conservés par affectation. Ne pas confondre suppression du SQL répété et suppression de toute croissance.
- **Attributions partagées** : les droits de classe ne sont plus relus pour chaque enfant ; observations, attributions et suppressions individuelles continuent à croître avec la sélection. Une écriture groupée serait un changement plus délicat, à traiter séparément avec les versions personnelles et la journalisation.
- **Référentiels** : consultation, adaptations et correspondances conservent des nombres de requêtes bornés dans les jeux exercés. Leur HTML et certaines recherches dans les contenus annuels croissent avec les compétences et les adoptions. Les bascules successives de bases, des ajouts nombreux et des correspondances nombreuses ne font pas partie des jeux chronométrés ; leurs règles sont couvertes par la suite fonctionnelle.
- **Années antérieures** : la sélection de la scolarité la plus récente et la lecture annuelle sont vérifiées par tests. Les gros instantanés clos peuvent produire de grandes expressions SQL `CASE` dans `observations_classe` ; aucun temps extrapolé n’est annoncé pour 30 élèves × 417 états annuels clos. Cette qualification doit précéder une éventuelle modification de cette projection.
- **Sauvegarde/restauration** : le ZIP local est généré puis sa vérification est exercée avant confirmation, sans remplacement du paquet. Les copies, empreintes et compression croissent avec la base et les fichiers. Le parcours diffuse le fichier depuis un fichier temporaire ; pas d’ajout de fichier ZIP entier à la réponse en mémoire. La restauration effectivement appliquée, les gros volumes, les sauvegardes PostgreSQL et le stockage distant n’ont pas été chronométrés. Le quota PWA, OPFS et l’impression navigateur restent hors de cette campagne Django.

Aucune refonte des parcours, migration, réduction des droits, changement des règles annuelles ou nouvelle fonction accessible. Le Guide pratique ne change pas ; les notes techniques et le journal des corrections rendent le bilan retrouvable.

## Vérifications et application

Les tests de performance ciblés portent sur la croissance des requêtes, sans seuil de temps fragile : listes avec 30 élèves ; ancienne et nouvelle scolarité ; 31 acquisitions et libellés annuels ; traces sans photo et avec photo ; 30 responsables ; candidats futurs, terminés, suspendus et dont l’affectation se termine aujourd’hui ; sélection partagée et refus d’un enfant hors classe. Les tests fonctionnels existants vérifient les droits, les écoles, les années, les carnets et les versions personnelles.

- `python manage.py test` : **796 tests réussis**, avec les dépendances facultatives du second facteur installées, Django 6.1.1 / SQLite ; 11 tests ciblés de performance compris dans cette suite.
- `makemigrations --check --dry-run` : aucune migration à créer.
- `pip check`, compilation Python du protocole, syntaxe des scripts shell et `git diff --check` : réussis.
- Les séries principales et complémentaires ont été exécutées sur le code de départ puis sur les corrections ; 205 paires de mesures dans le CSV et les deux JSON.
- Vérification des patchs : application séquentielle avec `git am` sur une copie propre de `main`, puis comparaison de l’arbre final.
- Non exécutés ici : tests PostgreSQL et variante Django 5.2 (à confirmer par la CI du dépôt), construction Hugo (aucun contenu du site modifié, Hugo absent), mesures navigateur (Chromium absent, installation indisponible). Aucune nouvelle mesure applicative interne sur Render.

Sept patchs : un protocole de mesure, cinq corrections indépendantes dans l’ordre indiqué, puis ce bilan et les notes README/CHANGELOG. Appliquer **toute la série dans l’ordre** : les tests partagent `suivi/tests_performance.py`.

```sh
unzip audit-performance-petits-pas.zip -d /tmp/audit-performance-petits-pas
git am /tmp/audit-performance-petits-pas/patchs/*.patch
```

La base de départ a été revérifiée sur le dépôt public : `3e8af5998d3b5c8673164173db385637c50e6b8a`. Aucun push, déploiement ni modification de données d’école n’a été effectué.
