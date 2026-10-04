+++
title = "Télécharger le programme autonome"
description = "Trouver la version de test adaptée à son ordinateur."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["télécharger", "version", "Linux", "Windows", "logiciel autonome"]
prerequis = "Disposer d’un ordinateur sous Ubuntu ou Windows ; utiliser des données fictives pour les essais."
depart = "Versions publiées de Petits Pas sur GitHub"
statut = "disponible"
+++

## Choisir un téléchargement

Ouvrez les [versions de Petits Pas](https://github.com/emmanuelagullo/petits-pas/releases)
avec la personne qui organise votre essai. La version **0.7** et les versions
suivantes proposent un installateur Windows. Repérez le fichier adapté à votre
ordinateur :

| Votre ordinateur | Fichier à choisir | Que faire ensuite ? |
| --- | --- | --- |
| Windows (64 bits) | `PetitsPas-Setup-…-x64.exe`, s’il est proposé | Ouvrir ce fichier et suivre l’assistant d’installation. |
| Ubuntu (Linux 64 bits) | `PetitsPas-linux.tar.gz` | Extraire le dossier ; suivre la fiche d’installation Ubuntu. |

Si la version ne propose que `PetitsPas-windows.zip` pour Windows, il s’agit
d’une ancienne méthode d’installation qui demande des manipulations
techniques. Ne l’utilisez pas pour une première installation accompagnée :
demandez le nouvel installateur à la personne qui organise votre essai.
L’archive Windows reste disponible pour les vérifications de l’équipe
technique. La version 0.6 utilise encore cette ancienne méthode.

Les fichiers **Source code** sont le code du projet, pas le programme prêt
à installer. Un fichier transmis pour un essai avant publication peut être
contenu dans une archive supplémentaire : décompressez celle-ci pour trouver
l’installateur Windows. Les versions publiées présentent directement les
fichiers à télécharger.

Poursuivez avec la [fiche d’installation et de mise à jour]({{< relref "/guide/local/installer-programme.md" >}}).
Le programme et les données de l’école sont conservés séparément : installer
une nouvelle version du programme ne supprime pas l’école ni ses sauvegardes.
Le numéro de la version installée est visible dans Petits Pas. Un fichier
transmis pour un essai avant publication peut porter une mention « dev » :
elle aide la personne qui organise l’essai à reconnaître exactement ce
programme.
