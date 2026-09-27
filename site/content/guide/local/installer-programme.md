+++
title = "Installer ou mettre à jour le programme autonome"
description = "Installer Petits Pas sur un ordinateur et retrouver l’école après une mise à jour."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["installer", "mettre à jour", "Ubuntu", "Windows", "revenir à une version"]
prerequis = "Disposer d’un ordinateur compatible et d’une version de test adaptée à son système."
depart = "Fichier d’installation téléchargé sur l’ordinateur"
statut = "partiel"
+++

## Sur Windows : installer et ouvrir

1. Depuis la [page de téléchargement]({{< relref "/guide/local/telecharger-programme.md" >}}),
   choisissez **PetitsPas-Setup-…-x64.exe** dans une préversion de test qui le
   propose. Si le fichier provient d’un essai transmis par l’équipe du projet,
   décompressez d’abord le téléchargement : vous trouverez le même fichier à
   ouvrir à l’intérieur. Les versions qui ne proposent qu’une archive ZIP
   correspondent à une ancienne méthode d’installation ; demandez le nouvel
   installateur à la personne qui organise votre essai.
2. Fermez Petits Pas s’il est déjà ouvert. Ouvrez le fichier téléchargé et
   suivez les écrans de l’assistant. Aucun mot de passe administrateur n’est
   nécessaire. Le programme apparaît ensuite dans le menu **Démarrer** sous
   le nom **Petits Pas**.
3. Ouvrez **Petits Pas** depuis le menu Démarrer. Lors du premier démarrage,
   l’écran **Installer Petits Pas** permet de créer l’école et son premier
   compte. Conservez les identifiants choisis.

Une fenêtre noire peut aussi s’ouvrir au démarrage dans cette version de
test : elle affiche des informations techniques et accompagne le programme.
Laissez-la ouverte pendant que vous utilisez Petits Pas.
Si Petits Pas ne s’ouvre pas ou reste bloqué, notez ce qui apparaît dans
cette fenêtre et transmettez-le à la personne qui accompagne votre essai.

## Sur Windows : mettre à jour ou retirer le programme

[Téléchargez une sauvegarde de l’école]({{< relref "/guide/local/sauvegarder-paquet.md" >}})
avant la mise à jour. Fermez Petits Pas, puis ouvrez le nouvel installateur
**PetitsPas-Setup-…-x64.exe**. S’il détecte une installation précédente faite
avec cet assistant, il indique la version déjà présente et demande si vous
souhaitez la remplacer. Une installation plus ancienne, réalisée avec un
autre programme d’installation, peut ne pas être détectée : le raccourci
**Petits Pas** du menu Démarrer ouvrira ensuite la nouvelle version.

Retrouvez votre école et vos comptes en ouvrant Petits Pas. Installer ou
désinstaller le **programme** ne supprime pas les données de l’école ni les
sauvegardes. Pour retirer le programme, utilisez **Paramètres → Applications →
Applications installées → Petits Pas → Désinstaller**. Ne supprimez pas le
dossier des données de l’école.

Si la nouvelle version pose problème, fermez-la et contactez la personne qui
accompagne votre essai avant de réinstaller une version plus ancienne :
une modification du format des données peut empêcher celle-ci de rouvrir
l’école. Il n’existe pas encore de bouton de retour à la version précédente
dans l’installateur graphique.

## Sur Ubuntu

Après avoir [téléchargé l’archive Linux]({{< relref "/guide/local/telecharger-programme.md" >}}),
extrayez-la entièrement. Dans un terminal ouvert dans le dossier `PetitsPas`
extrait, exécutez `bash installer-paquet-linux.sh`, puis ouvrez **Petits Pas**
depuis le menu des applications. GTK, WebKit2 et les bibliothèques nécessaires
aux PDF doivent être disponibles sur l’ordinateur.

Pour mettre à jour, [sauvegardez l’école]({{< relref "/guide/local/sauvegarder-paquet.md" >}}),
fermez l’application, extrayez la nouvelle archive et relancez son
installateur. Les outils Linux de gestion des versions sont décrits dans la
[documentation technique du dépôt](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/README.md).

## Avant tout usage réel

Ces versions sont encore des prototypes de test. Faites vos essais avec des
données fictives ; l’usage de données réelles demande une qualification
préalable. Le programme autonome ne synchronise pas l’école entre plusieurs
ordinateurs.
