+++
title = "Utiliser le mode autonome local"
description = "Installer le programme autonome et protéger ses données locales."
+++

En mode hébergé, on ouvre Petits Pas dans un navigateur et l’école est
conservée sur un serveur distant ; la démonstration publique est un exemple
de ce fonctionnement, avec des données fictives et temporaires. Le mode
autonome local installe le programme et les données sur un seul poste, sans
connexion au serveur distant. L’interface s’ouvre dans une fenêtre dédiée.
Django fonctionne uniquement sur ce poste pendant l’utilisation ; les données
de l’école résident dans un **paquet autonome** distinct du programme.

- [Installer, mettre à jour ou revenir à une version]({{< relref "/guide/local/installer-programme.md" >}}).
- [Télécharger une sauvegarde du paquet]({{< relref "/guide/local/sauvegarder-paquet.md" >}}).
- [Vérifier et restaurer une sauvegarde]({{< relref "/guide/local/restaurer-paquet.md" >}}).

## Où se trouvent les sauvegardes ?

Une direction voit la même page **Gérer l’école** dans les deux modes. Seule
l’installation locale affiche le bouton **Sauvegardes locales** : elle peut
exporter et restaurer son paquet depuis l’application. En mode hébergé,
l’hébergeur ou la DSI assure la sauvegarde et la reprise de l’instance ; les
utilisateurs n’ont donc pas de bouton pour restaurer la base partagée.

{{< comparaison-modes >}}

La [fiche de sauvegarde]({{< relref "/guide/local/sauvegarder-paquet.md" >}})
montre également l’écran de téléchargement et de restauration du mode local.

Ce mode ne synchronise pas les données entre ordinateurs. Le programme et sa
distribution restent en développement ; l’usage de données réelles demande
une qualification préalable. Pour travailler à plusieurs sur une même école,
consultez la [présentation du profil hébergé]({{< relref "/dsi/" >}}).
