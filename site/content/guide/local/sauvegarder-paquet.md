+++
title = "Télécharger une sauvegarde du paquet local"
description = "Conserver une copie de l’école, de ses médias et de sa clé."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["sauvegarde", "exporter", "ZIP", "SQLite", "photos"]
prerequis = "Petits Pas fonctionne en mode local ; votre compte exerce la direction de l’école."
depart = "Gérer l’école → Sauvegardes locales"
statut = "disponible"
+++

## Télécharger et conserver

La commande apparaît dans le programme autonome et dans l’application dans le navigateur,
pour un compte de direction. En mode hébergé, l’hébergeur ou la DSI gère la sauvegarde
de la base partagée et des médias : la page **Gérer l’école** n’affiche pas
**Sauvegardes locales**. La [comparaison des interfaces]({{< relref "/guide/local/" >}})
montre cette différence.

{{< capture-guide src="captures/guide/local/sauvegardes.png" alt="Page Sauvegardes locales d’une école fictive, avec les commandes de téléchargement et de vérification du ZIP" caption="Les sauvegardes locales sont réservées à la direction dans les modes locaux." >}}

Dans **Gérer l’école**, ouvrez **Sauvegardes locales**. Dans le navigateur,
vous pouvez aussi passer par **Outils de l’application → Ouvrir les
sauvegardes locales**. Cliquez sur **Télécharger une sauvegarde**. Enregistrez le fichier ZIP dans un emplacement
protégé, distinct du dossier du programme et du paquet de travail. Il contient
la base de données SQLite, les médias et la clé nécessaire à la reprise :
toute personne possédant cette archive peut accéder aux données qu’elle contient.

Vérifiez que le téléchargement est terminé et que le fichier peut être retrouvé
avant de compter sur cette copie. Répétez l’opération selon les besoins de
l’école, notamment avant une mise à jour du programme. Le téléchargement
ne supprime pas le paquet en cours.

La page indique la date du dernier ZIP préparé sur cet appareil. Elle propose
de télécharger une nouvelle copie si aucun export n’a été enregistré ou après sept jours.
Cette date ne prouve pas que le fichier a été conservé : gardez une copie hors
de l’appareil, selon l’organisation choisie par l’école.

Le ZIP permet aussi un transfert entre programme autonome et navigateur,
avec une version compatible. Continuez ensuite les saisies sur une seule copie :
les appareils ne se synchronisent pas. Voir l’[application dans le navigateur]({{< relref "/guide/local/essayer-navigateur.md" >}})
pour ses limites et son parcours de restauration.

Dans le navigateur, l’[état de récupération]({{< relref "/guide/local/essayer-navigateur" >}}#mettre-à-jour-et-récupérer) est un autre export. Il peut remonter à l’état conservé avant le dernier remplacement.

Pour [restaurer une archive]({{< relref "/guide/local/restaurer-paquet.md" >}}), revenez dans la même page.
Les installations avec serveur disposent d’une autre procédure de sauvegarde,
décrite dans la [rubrique Institutions et hébergement]({{< relref "/dsi/" >}}).
