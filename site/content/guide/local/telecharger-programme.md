+++
title = "Télécharger le programme autonome"
description = "Trouver les versions publiques Linux et Windows et choisir l’archive adaptée."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["télécharger", "version", "release", "Linux", "Windows", "archive", "logiciel autonome"]
prerequis = "Disposer d’un ordinateur sous Ubuntu ou Windows ; aucune donnée réelle pour les essais du prototype."
depart = "Versions publiques de Petits Pas sur GitHub"
statut = "partiel"
+++

## Trouver une version publiée

Les téléchargements publics du programme autonome sont regroupés sur la page
[Versions publiées de Petits Pas sur GitHub](https://github.com/emmanuelagullo/petits-pas/releases).
Ouvrez une version explicitement marquée comme **préversion de test**, puis,
dans **Assets**, choisissez l’archive correspondant à votre système :

| Système | Archive à télécharger | Après téléchargement |
| --- | --- | --- |
| Ubuntu (Linux x86-64) | `PetitsPas-linux.tar.gz` | Extraire le dossier `PetitsPas` ; GTK, WebKit2 et Pango sont nécessaires. |
| Windows (64 bits) | `PetitsPas-windows.zip` | Décompresser intégralement le dossier `PetitsPas`. |

Les fichiers intitulés **Source code** sont les sources du programme, pas
les archives prêtes à lancer. Les artefacts temporaires GitHub Actions servent
aux essais avant publication ; la page **Versions publiées** fournit les
archives retenues pour la diffusion. Si aucune version avec ces deux fichiers
n’apparaît encore, le programme autonome n’est pas encore publié pour ces
deux systèmes.

Un même tag Git est poussé sur GitHub et sur le [dépôt de référence GitLab
Inria](https://gitlab.inria.fr/petits-pas/petits-pas/-/releases). Une release
GitLab peut également présenter des liens vers les mêmes archives GitHub.

Après extraction, suivez la [fiche d’installation et de mise à jour]({{< relref "/guide/local/installer-programme.md" >}}).
Les archives ne contiennent pas les données de votre école : une mise à jour
du programme ne remplace pas le paquet autonome et ses sauvegardes.
