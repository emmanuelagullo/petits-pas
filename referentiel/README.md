# Contenus du référentiel

`trame-cycle1.yaml` est une trame de travail, sans statut de référentiel officiel.
Les codes des compétences et des formulations servent à conserver leur identité
lors d'un nouvel import. Une compétence peut n'avoir ni icône ni formulation.

```yaml
- code: LANG-01
  libelle: "J'ose parler devant les autres"
  niveau: PS
  icone: parler
  formulations:
    - code: LANG-01-F01
      texte: "<prenom> prend la parole pendant un échange."
```

`icones.yaml` associe un identifiant indépendant des compétences à un fichier
statique. Les trois SVG de `static/referentiel/icones/` sont des dessins originaux
simples créés pour Petits Pas et distribués sous `CC-BY-SA-4.0`. Ils n'incorporent
aucune ressource tierce. Ils sont versionnés dans Git et inclus dans le paquet
autonome. L'association de quelques compétences sert d'exemple ; le catalogue
n'a pas vocation à illustrer intégralement la trame.

La migration ne réimporte pas automatiquement le référentiel d'une école
existante. Les équipes peuvent choisir les icônes depuis l'interface, ou
mettre à jour leur YAML puis l'importer avec :

```sh
python3 manage.py charger_referentiel chemin/vers/referentiel.yaml --ecole ID
```

Un import met aussi à jour les libellés et formulations fournis par ce fichier.
Il faut donc utiliser le référentiel choisi pour l'école, plutôt que réimporter
la trame d'exemple uniquement pour obtenir ses trois associations d'icônes.

L'import met à jour les contenus fournis. Les adaptations école/classe sont
conservées séparément. Une formulation locale conserve son lien d'origine ;
une mise à jour de la source n'écrase pas son texte adapté. Masquer une
proposition conserve également son identité. Les textes déjà enregistrés dans
les traces ne sont pas modifiés par l'import.
