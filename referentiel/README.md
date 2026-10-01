# Contenus du référentiel

`trame-cycle1.yaml` est une trame de travail, sans statut de référentiel officiel.
L'audit des contenus, de leur provenance et des offres à préparer est consigné
dans [CONTENUS-REFERENTIELS.org](../CONTENUS-REFERENTIELS.org) (#CR1).
Il ne remplace ni n'importe cette trame ; les deux versions sous `exemples/`
restent exclusivement fictives.
La préparation de la couverture et l'échantillon à relire figurent dans
[PREPARATION-CONTENUS-REFERENTIELS.org](../PREPARATION-CONTENUS-REFERENTIELS.org)
(#CR2), avec le [registre de références et de sens](REGISTRE-CONTENUS-CR2.org).
Ces documents préparent les contenus ; ils ne publient pas de source au catalogue.
Deux [fichiers pilotes pour relecture pédagogique](pilotes/NOTICE-CR3.org)
(#CR3) rendent cet échantillon importable : quatre objectifs officiels et douze
repères reformulés. Leur couverture est partielle ; la notice et le registre
accompagnent les fichiers. Ils ne sont pas importés automatiquement.
Pour le chargement historique dans une école non reprise, les codes des
compétences et formulations servent à retrouver les éléments lors d'un import.
Pour l'import versionné au catalogue, l'identité d'une compétence est déclarée
explicitement, indépendamment de son code : voir
[IMPORT-SOURCES-REFERENTIELS.org](../IMPORT-SOURCES-REFERENTIELS.org). Une compétence peut n'avoir ni icône ni formulation.

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
existante. Les équipes peuvent choisir les icônes depuis l'interface. La commande ci-dessous
est réservée aux écoles qui n'ont pas encore été préparées aux référentiels
annuels ; elle est refusée pour une école déjà reprise :

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

## Éditions couvrant les objectifs du cycle 1

Les [éditions 2026.1](cycle1/NOTICE.org) proposent les 426 objectifs inventoriés
(six domaines et EVAR) et une offre étayée de douze repères supplémentaires.
Leur [couverture](cycle1/COUVERTURE.org) et leur [registre](cycle1/REGISTRE.csv)
accompagnent les YAML. Ces éditions restent provisoires pour relecture.
