# Contribuer à Petits Pas

Merci de l'intérêt porté à Petits Pas. Le projet accueille les corrections,
les propositions fonctionnelles, les retours d'usage et les contributions au
code ou à la documentation.

## Licence des contributions

Sauf mention explicite acceptée avant la contribution, toute contribution au
code est proposée sous la licence `AGPL-3.0-or-later` et toute contribution à
la documentation publique sous la licence `CC-BY-SA-4.0`.

En soumettant une contribution, son auteur confirme qu'il a le droit de la
publier sous la licence correspondante. Aucun transfert de copyright n'est
demandé.

Les photographies, productions d'enfants, données d'établissement ou autres
données personnelles ne doivent jamais être ajoutées au dépôt. Les exemples,
tests, démonstrations et captures doivent employer exclusivement des données
fictives.

## Vérifications

Avant de proposer une modification, exécuter lorsque cela s'applique :

```sh
python3 manage.py collectstatic --noinput
python3 manage.py test --settings=carnet.settings_tests --durations 30 --timing
python3 manage.py makemigrations --check --dry-run
bash -n start-atelier.sh start-persistent.sh start-render.sh scripts/*.sh
hugo --source site --minify
git diff --check
```

`carnet.settings_tests` accélère uniquement le hachage des mots de passe
fictifs. Il doit être choisi explicitement : ne pas l'utiliser pour lancer
le service, préparer une école ou construire une distribution. Les tests
d'authentification ordinaire et le scénario d'export complet d'école gardent
le hachage Django par défaut ; les sous-processus d'export utilisent
`carnet.settings`. Pour comparer avec les paramètres habituels, omettre
`--settings=carnet.settings_tests`.

`--durations 30` affiche les trente tests les plus lents ; `--timing`
distingue notamment la préparation des bases de leur utilisation. Les fixtures
de classe ne sont pas attribuées à chaque durée individuelle. Comparer les
durées à environnement équivalent.

Les tests de scripts ne sont pas découverts par `manage.py test`. La CI
exécute leurs commandes dédiées : notamment
`python3 -m unittest discover -s scripts -p test_version_application.py`
dans les jobs Django, et
`node --test scripts/test_transport_pwa.cjs scripts/test_recherche_referentiel.cjs`
dans le job PWA, qui dispose déjà de Node.

Les vérifications GitLab marquées `interruptible` peuvent être annulées
lorsqu'un nouveau commit arrive sur la même branche. Les déploiements de
vérification et les publications ne le sont pas. Sur GitHub, une nouvelle
construction de la même branche remplace la précédente ; les constructions
de tags ne sont pas annulées automatiquement.
