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
python3 manage.py test
python3 manage.py makemigrations --check --dry-run
bash -n start-atelier.sh start-persistent.sh start-render.sh scripts/*.sh
hugo --source site --minify
git diff --check
```
