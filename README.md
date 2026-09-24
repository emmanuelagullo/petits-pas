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

### Prototype de fenêtre locale (#L1)

Avec les dépendances Python du projet installées :

```sh
python3 -m pip install -r requirements-local.txt
python3 scripts/lancer-local.py
# Ou, pour un autre emplacement :
python3 scripts/lancer-local.py --paquet /chemin/vers/mon-paquet
```

Le lanceur ouvre PyWebView sur Django, lié uniquement à `127.0.0.1` sur un
port libre. Fermer la fenêtre arrête le serveur. Par défaut, il crée
`./paquet-autonome/` à la racine du projet, avec `carnet.sqlite3`, `media/` et
`secret-key` ; ce répertoire est exclu de Git. Le chemin se règle aussi par
`PETITS_PAS_PAQUET_AUTONOME` (l'option `--paquet` a priorité). Un chemin
relatif est interprété depuis le répertoire de lancement. Les migrations
s'appliquent automatiquement à la base de ce paquet. Les anciennes données
de développement à la racine du dépôt ne sont pas importées ; aucun compte
ni jeu de démonstration n'est créé. Le courrier est désactivé.

Ce jalon est un prototype à lancer depuis les sources, sans installateur :
le téléchargement des PDF dépend du moteur Web installé. Conserver ensemble
les trois éléments du paquet pour préparer une sauvegarde ou un transfert ;
une copie faite pendant que l'application tourne peut être incohérente.
Les jalons suivants traiteront la sauvegarde, le premier compte et la
distribution.

## Site public

Le site de présentation est construit avec Hugo depuis le répertoire `site/` :

```sh
sh scripts/preparer-site.sh
python3 scripts/verifier-guide-pratique.py
hugo --source site --minify
```

Hugo rend directement les contenus Markdown et Org-mode. Seuls les documents
explicitement placés dans `site/content/` sont publiés. Le contrôle préalable
vérifie les métadonnées des fiches pratiques, leurs liens internes et la
cohérence entre les captures utilisées et les scénarios fictifs déclarés.

## Licence

Le code de Petits Pas est distribué sous licence
[GNU Affero General Public License, version 3 ou ultérieure](LICENSE)
(`AGPL-3.0-or-later`). Cette licence autorise notamment l'usage, l'étude, la
modification, la redistribution et l'auto-hébergement du logiciel.

La politique applicable à la documentation, aux illustrations et aux données
est détaillée dans [CONTENUS-ET-LICENCES.md](CONTENUS-ET-LICENCES.md).
