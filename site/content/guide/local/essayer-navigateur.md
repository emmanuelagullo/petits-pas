+++
title = "Essayer le prototype dans le navigateur"
description = "Tester les sauvegardes et l’impression sans serveur applicatif."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["PWA", "hors ligne", "navigateur", "transfert", "PDF"]
prerequis = "Une installation d’essai vous a été fournie ; utilisez uniquement des données fictives."
depart = "Page d’accueil du prototype dans Chromium"
statut = "partiel"
+++

Ce prototype conserve l’école dans le navigateur de cet appareil. Il peut
fonctionner hors ligne après le premier téléchargement. Il ne remplace pas
encore le programme Windows ou Linux : utilisez **uniquement des données
fictives**. Les tablettes et les grands carnets restent à vérifier.

## Sauvegarder et transférer

Avec un compte de direction, ouvrez **Gérer l’école → Sauvegardes locales**,
puis **Télécharger une sauvegarde**. Le ZIP contient l’école, les comptes,
les carnets, les photos et la clé locale. Conservez-le dans un lieu protégé.
Il peut être restauré dans le programme autonome avec une version compatible.

Pour importer un ZIP issu du programme autonome, choisissez-le dans
**Restaurer une sauvegarde**, puis cliquez sur **Vérifier la sauvegarde**.
Vérifiez les détails, puis choisissez **Annuler** ou **Confirmer la
restauration**. La confirmation remplace les données présentes sur cet appareil.
Reconnectez-vous avec un compte de la sauvegarde importée.

Dans ce prototype, un ZIP téléchargé est limité à 20 Mio à l’import et son
contenu à 64 Mio après décompression. Le stockage de travail reste limité à
16 Mio compressés ; une erreur de stockage impose de fermer puis rouvrir
l’application pour retrouver le dernier état enregistré.

## Imprimer ou enregistrer un PDF

Depuis le carnet ou une grille, ouvrez **Préparer l’impression / PDF**, puis
**Imprimer / enregistrer en PDF**. Choisissez « Enregistrer au format PDF »
dans la fenêtre d’impression si le navigateur le propose. Les photos restent
sur cet appareil. La mise en page peut différer de celle du programme autonome.

La préparation pour plusieurs enfants réunit leurs carnets dans un seul
document à imprimer ; elle ne produit pas un ZIP de PDF séparés.

## Mettre à jour et récupérer

Téléchargez d’abord une sauvegarde. **Vérifier les mises à jour** recherche une
nouvelle version ; **Appliquer la mise à jour** l’active et redémarre
l’application. Une version téléchargée peut aussi s’activer au prochain
lancement, après fermeture de tous les onglets. Ne déplacez pas l’installation
vers une autre adresse : les données du navigateur dépendent de cette adresse.

**Exporter l’état de récupération** télécharge l’état conservé avant la
dernière mise à jour ou restauration ; si aucun remplacement n’a eu lieu,
il télécharge l’état actuel. Cet état peut être plus ancien que les dernières
saisies. En fonctionnement normal, l’export est réservé à la direction.
Si l’application ne démarre plus, la récupération reste accessible sans
connexion : elle est destinée à la personne qui possède ce profil de
navigateur. Le ZIP contient toutes les données de l’école.

Effacer le profil du navigateur ou les données du site peut supprimer
l’école et son état de récupération. Le bouton **Protéger le stockage local**
ne remplace jamais une sauvegarde externe. N’utilisez pas un profil partagé
avec des personnes qui ne doivent pas accéder aux données de l’école.
