# Pas communs — #SOC2

Petits Pas dépend maintenant de `pas-communs` 0.1.0 pour le moteur ZIP/SQLite.
La façade `suivi.paquet_local` conserve l'API, les confirmations en mémoire,
le rappel d'export local et les métadonnées de projection. Droits, exports,
imports et sélection des secrets restent dans Petits Pas. Aucun modèle Django,
format historique ou nom de stockage navigateur n'est déplacé.

## Installer

Le wheel public est fixé par URL et SHA-256 dans `requirements-communs.txt`,
inclus par les profils serveur, bureau et navigateur. Installer les dépendances
habituelles suffit. Pas de service additionnel, de Git ni de PyPI à configurer.
La première publication du wheel `0.1.0` de Pas communs doit précéder l'adoption
et le déploiement de ce patch. Un téléchargement manquant ou altéré est refusé.

Avant cette publication, les essais peuvent employer le wheel local candidat :
installer les autres dépendances avec un fichier temporaire privé d'inclusion du
socle, puis `pip install /chemin/pas_communs-0.1.0-py3-none-any.whl`.
Ne pas committer de chemin local ni de dépendance à une branche mobile.
En développement conjoint : `pip install -e ../pas-communs` après préparation du
backend de construction. Les releases utilisent toujours le wheel fixé.

## Programme et PWA

PyInstaller collecte le module `pas_communs` installé par le profil bureau.
Le constructeur PWA inclut le même wheel pur dans ses ressources, contrôlé
par l'empreinte épinglée. `--wheels` doit aussi contenir ce wheel exact ; ce
cache peut être utilisé avant publication ou hors réseau. Une version différente
ou absente est refusée. Ne pas distribuer une copie du moteur dans application.zip.

Les anciens ZIP Petits Pas sans champ `application` sont acceptés uniquement avec
leur format historique. Les nouveaux ajoutent `application: petits-pas` sans
changer version, noms de fichiers ni métadonnées d'export. Les anciens validateurs
restent capables de les lire. Aucun relèvement des plafonds PWA n'est effectué.
Les manifestes OPFS historiques sans identité explicite restent lisibles ; aucun
changement de leurs noms ni de leurs espaces n'est nécessaire.

## Vérifier

Conserver les tests `test_paquet_local`, `test_transferts_pwa`, les tests Django
exports/imports, sauvegardes et aperçus, les essais PWA et les constructions
Windows/Linux. La CI du socle ne remplace pas la qualification du produit.
La CI `0.10` et sa publication doivent rester sur le commit préparé avant #SOC2.
