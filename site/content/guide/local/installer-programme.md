+++
title = "Installer ou mettre à jour le programme autonome"
description = "Installer Petits Pas sur un ordinateur et retrouver l’école après une mise à jour."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["installer", "mettre à jour", "Windows", "Mac", "macOS", "Ubuntu", "revenir à une version"]
prerequis = "Disposer d’un ordinateur Windows, d’un Mac à puce Apple ou d’un ordinateur Ubuntu, et d’une version de test adaptée à son système."
depart = "Fichier d’installation téléchargé sur l’ordinateur"
statut = "disponible"
+++

## Sur Windows : installer et ouvrir

1. Depuis la [page de téléchargement]({{< relref "/guide/local/telecharger-programme.md" >}}),
   choisissez **PetitsPas-Setup-…-x64.exe** dans la version choisie. Si le fichier
   provient d’un essai transmis par l’équipe du projet,
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
   compte. Conservez les identifiants choisis. Les nouvelles versions issues du
   démarrage simplifié proposent **Préparer aussi ma première classe**, coché :
   nom, année et référentiel permettent d’ouvrir directement l’ajout des élèves.
   Vous recevez les droits de direction et de responsable de cette classe dans
   l’application. Décochez pour créer seulement l’école. La release 0.7 ne
   comporte pas encore cette option ; créez la classe après connexion et
   affectez son responsable.

**Si Windows affiche « Windows a protégé votre ordinateur ».** L’installateur
n’est pas encore signé numériquement : ce message ne signifie pas que le fichier est
dangereux, mais Windows ne le connaît pas. Si vous l’avez téléchargé depuis les versions
officielles du projet, cliquez sur **Informations complémentaires**, puis sur
**Exécuter quand même**.

**Si la fenêtre reste vide ou ne s’ouvre pas.** Petits Pas utilise le composant
gratuit de Microsoft **WebView2**, présent sur la plupart des ordinateurs récents.
Quand il manque, l’installateur ou Petits Pas le signale parfois, mais pas toujours.
Ouvrez la [page de téléchargement de Microsoft](https://developer.microsoft.com/microsoft-edge/webview2/),
téléchargez **Evergreen Bootstrapper** (ou **Evergreen Standalone Installer** si
l’ordinateur n’a pas accès à Internet), lancez-le, puis rouvrez Petits Pas.

Si Petits Pas ne s’ouvre pas, un message indique où trouver le diagnostic.
Notez ce message et transmettez-le à la personne qui accompagne votre essai.
Si la fenêtre reste bloquée sans message, indiquez ce que vous faisiez au
moment du blocage.

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

La version du programme est indiquée en bas de chaque page de Petits Pas.
Si une mise à jour de l’école est nécessaire à l’ouverture, un message vous
invite à patienter ; un second message confirme sa fin avant l’ouverture.
En cas d’échec, relevez le chemin du diagnostic indiqué à l’écran et
transmettez-le à la personne qui accompagne votre essai. Les données
précédentes sont copiées avant les changements nécessaires à cette mise à jour.

Si la nouvelle version pose problème, fermez-la et contactez la personne qui
accompagne votre essai avant de réinstaller une version plus ancienne :
une modification du format des données peut empêcher celle-ci de rouvrir
l’école. Il n’existe pas encore de bouton de retour à la version précédente
dans l’installateur graphique.

## Sur Mac : installer et ouvrir

Le programme pour Mac est une **version d’essai** : il est construit automatiquement,
mais l’équipe ne l’a pas encore essayé sur un Mac réel. Il fonctionne sur les Mac à
**puce Apple** (M1 ou plus récent) avec **macOS 15 ou plus récent**. Les anciens Mac à
processeur Intel ne sont pas pris en charge. Pour le vérifier : menu Pomme, puis
**À propos de ce Mac**, ligne **Puce** ; la version de macOS figure dans
**Réglages Système → Général → Informations**.

1. Depuis la [page de téléchargement]({{< relref "/guide/local/telecharger-programme.md" >}}),
   choisissez **PetitsPas-macos-arm64.dmg** dans la version choisie, puis ouvrez
   ce fichier.
2. Dans la fenêtre qui s’ouvre, glissez **Petits Pas** sur le dossier **Applications**,
   puis éjectez l’image disque.
3. Ouvrez **Petits Pas** depuis le dossier Applications. Au premier lancement, macOS
   indique qu’il ne peut pas vérifier le programme, car il n’est pas encore signé
   par Apple. Ouvrez **Réglages Système → Confidentialité et sécurité**, descendez
   jusqu’au message signalant que Petits Pas a été bloqué, cliquez sur
   **Ouvrir quand même**, puis confirmez avec votre mot de passe. Les intitulés peuvent
   varier selon la version de macOS ; cette étape peut être demandée de nouveau
   après une mise à jour du programme.
4. Lors du premier démarrage, l’écran **Installer Petits Pas** permet de créer l’école
   et son premier compte, comme sous Windows. Conservez les identifiants choisis.

Si Petits Pas ne s’ouvre pas, une alerte indique où trouver le diagnostic : le fichier
`dernier-demarrage.log` du dossier `~/Library/Application Support/petits-pas/logs`.
Notez ce message et transmettez-le à la personne qui accompagne votre essai, sans
joindre de données d’élèves.

## Sur Mac : mettre à jour ou retirer le programme

[Téléchargez une sauvegarde de l’école]({{< relref "/guide/local/sauvegarder-paquet.md" >}})
avant la mise à jour. Fermez Petits Pas, ouvrez le nouveau fichier **.dmg**, glissez
**Petits Pas** dans **Applications** et choisissez **Remplacer**. Vos données sont
conservées hors du programme, dans `~/Library/Application Support/petits-pas/paquet-autonome` :
ne les supprimez pas. Pour retirer le programme, glissez **Petits Pas** du dossier
Applications vers la Corbeille ; l’école et ses sauvegardes restent en place.

Comme sous Windows, une modification du format des données peut empêcher une version
plus ancienne de rouvrir l’école : contactez la personne qui accompagne votre essai avant
de réinstaller une version plus ancienne.

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

Faites vos essais avec des données fictives. Avant d’utiliser des données
réelles, préparez avec l’école la [protection des données]({{< relref "/proteger-donnees/" >}})
et vérifiez le fonctionnement sur votre appareil. Le programme autonome ne synchronise pas l’école entre plusieurs
ordinateurs.

## Choisir le départ pédagogique

Les versions intégrant Suivi libre permettent aussi de démarrer avec des catégories seules. Ce choix concerne l’école et sa première classe ; il est indépendant du programme utilisé.

Voir [le suivi libre et ses règles]({{< relref "/guide/observer/ajouter-reussite" >}}).
