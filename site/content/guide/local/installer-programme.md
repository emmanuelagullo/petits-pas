+++
title = "Installer ou mettre à jour le programme autonome"
description = "Ouvrir Petits Pas sans serveur distant et gérer les versions installées."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["installer", "mettre à jour", "Ubuntu", "Windows", "revenir à une version", "nettoyer"]
prerequis = "Avoir téléchargé l’archive adaptée à Ubuntu ou Windows et disposer d’un ordinateur compatible."
depart = "Archive PetitsPas extraite sur l’ordinateur"
statut = "partiel"
+++

## Installer et ouvrir

[Téléchargez la version publiée]({{< relref "/guide/local/telecharger-programme.md" >}})
correspondant à votre système, puis extrayez-la entièrement. Pour essayer une
construction avant publication, les artefacts GitHub Actions comportent un
ZIP enveloppe supplémentaire à extraire ; ce n’est pas le cas des archives
publiées dans une release.

- **Ubuntu** : dans un terminal ouvert dans le dossier `PetitsPas` extrait,
  exécutez `bash installer-paquet-linux.sh`. Lancez ensuite **Petits Pas** depuis
  le menu des applications. GTK, WebKit2 et les bibliothèques de génération PDF
  doivent être disponibles sur l’ordinateur.
- **Windows** : ouvrez `Installer-PetitsPas.cmd` depuis le dossier `PetitsPas`
  extrait, puis lancez **Petits Pas** depuis le menu Démarrer.

À la première ouverture d’un paquet vide, l’écran **Installer Petits Pas**
permet de créer l’école et son premier compte de direction. Conservez les
identifiants choisis. Le paquet de données est créé séparément du programme,
par défaut sous `~/.local/share/petits-pas/paquet-autonome/` sur Linux ou
`%LOCALAPPDATA%\petits-pas\paquet-autonome` sous Windows. Sous Linux,
`$XDG_DATA_HOME` peut modifier ce chemin. Le programme doit être fermé avant
de changer de version.

## Mettre à jour ou revenir en arrière

Pour mettre à jour, extrayez une nouvelle archive et relancez son installateur.
Les données de l’école restent dans le même paquet. Depuis le dossier extrait,
vous pouvez consulter les versions et revenir à la précédente :

| Action | Ubuntu, terminal | Windows, terminal PowerShell |
| --- | --- | --- |
| Lister les versions | `bash gerer-versions-linux.sh --lister` | `.\Installer-PetitsPas.cmd -Action Lister` |
| Revenir à la précédente | `bash gerer-versions-linux.sh --revenir` | `.\Installer-PetitsPas.cmd -Action Revenir` |
| Retirer les versions plus anciennes | `bash gerer-versions-linux.sh --nettoyer` | `.\Installer-PetitsPas.cmd -Action Nettoyer` |

Le nettoyage conserve la version active et la précédente ainsi que les données
de l’école. Revenez à une ancienne version seulement si elle sait lire le format
actuel de la base : une mise à jour avec migration peut rendre ce retour
impossible. [Sauvegardez le paquet]({{< relref "/guide/local/sauvegarder-paquet.md" >}}) avant une mise à jour.

## Limites

Ces archives sont des prototypes propres à leur système, pas un installateur
universel. Leur validation sur chaque machine reste nécessaire. Les
[instructions détaillées du dépôt](https://gitlab.inria.fr/petits-pas/petits-pas/-/blob/main/README.md)
expliquent également le lancement depuis les sources et le choix d’un autre
emplacement de données.
