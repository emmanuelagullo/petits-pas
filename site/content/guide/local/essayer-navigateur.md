+++
title = "Essayer l’application dans le navigateur"
description = "Ouvrir Petits Pas, conserver son école et préparer les impressions."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["PWA", "hors ligne", "navigateur", "transfert", "PDF"]
prerequis = "Un navigateur compatible est nécessaire ; utilisez uniquement des données fictives pour les essais."
depart = "Page d’accueil de Petits Pas dans le navigateur"
statut = "disponible"
+++

Petits Pas conserve l’école dans le navigateur de cet appareil. Il peut
fonctionner hors ligne après le premier téléchargement. Utilisez **uniquement des données
fictives**. Les tablettes et les grands carnets restent à vérifier.

## Ouvrir et préparer l’école

L'adresse d'essai est [Petits Pas dans le navigateur](https://petits-pas.gitlabpages.inria.fr/petits-pas-pwa/).
Conservez cette adresse pour retrouver les données de ce navigateur.

Ouvrez cette adresse dans un navigateur compatible, puis attendez le premier chargement.
Sur une installation vide, **Installer Petits Pas** permet de créer l’école
et le premier compte personnel. Selon la version publiée, le formulaire propose
**Préparer aussi ma première classe**, coché par défaut. Indiquez son nom,
l’année scolaire et le référentiel ; vous deviendrez responsable de cette classe
et pourrez directement ajouter les élèves fictifs. Le référentiel est proposé
pour l’école et adopté par la classe. Décochez l’option pour préparer seulement
l’école. Si cette option est absente, connectez-vous, créez la classe puis
 affectez son responsable. Une CI réussie ne signifie pas que cette nouvelle
version a été publiée. Conservez cette adresse pour
les prochaines ouvertures. Chaque appareil garde sa propre école ; pour
transférer les données vers un autre appareil, utilisez une sauvegarde ZIP.
Une école créée lors d'un essai local sur l'ordinateur doit également être
transférée par un ZIP pour être retrouvée à cette nouvelle adresse.

## Installer et retrouver Petits Pas

Si **Installer Petits Pas** apparaît, il propose l’ajout d’une icône. Sinon,
ouvrez **Installation, stockage et mises à jour** pour voir les instructions
pour votre navigateur. Vous pouvez aussi continuer dans cet onglet.
Le premier chargement affiche les étapes de préparation ; attendez que l’école
s’ouvre. La version reste visible. Sur petit écran, les outils se replient pour
laisser de la place à l’application. Une difficulté de démarrage propose
**Réessayer** et la récupération, sans effacer les données.
Les installations Windows, Android et iPad sont à observer au fil des essais.

## Sauvegarder et transférer

Avec un compte de direction, ouvrez **Sauvegardes / transfert** ou **Gérer l’école → Sauvegardes locales**,
puis **Télécharger une sauvegarde**. Le ZIP contient l’école, les comptes,
les carnets, les photos et la clé locale. Conservez-le dans un lieu protégé.
Il peut être restauré dans le programme autonome avec une version compatible.

La page indique le dernier ZIP préparé sur cet appareil. Un rappel apparaît
pour la direction si aucun export n’a été enregistré ou après sept jours.
Vérifiez le téléchargement et gardez une copie hors de l’appareil : cette date
ne confirme pas que le fichier a été conservé. Après un transfert, continuez
les saisies sur une seule copie : les appareils ne se synchronisent pas.

Pour importer un ZIP issu du programme autonome, choisissez-le dans
**Restaurer une sauvegarde**, puis cliquez sur **Vérifier la sauvegarde**.
Vérifiez les détails, puis choisissez **Annuler** ou **Confirmer la
restauration**. La confirmation remplace les données présentes sur cet appareil.
Reconnectez-vous avec un compte de la sauvegarde importée.

Dans le navigateur, le contenu d’une sauvegarde est limité à 64 Mio après
décompression et son envoi à 70 Mio. Les données de travail sont également
limitées à 64 Mio avant compression. Le bandeau affiche le volume du dernier
état enregistré. À partir de 52 Mio, il conseille de télécharger une sauvegarde et de terminer
l’essai. Une erreur de stockage impose de fermer puis rouvrir l’application
pour retrouver le dernier état enregistré. Les consultations sans modification
ne réécrivent plus les photos. Depuis #PWA11, les photos enregistrées sont lues
à la demande, ce qui évite de toutes les garder en mémoire. Les sauvegardes et
restaurations utilisent encore des copies temporaires complètes ; la limite
reste donc la même. Vérifiez la version affichée dans l’aide.
Une nouvelle connexion peut être nécessaire
après 12 heures ; elle est toujours nécessaire après fermeture puis réouverture.

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

## Retrouver les nouveautés de votre version

La version est affichée en haut de Petits Pas. Ouvrez **Installation, stockage
et mises à jour**, puis **Voir les nouveautés**. Ces notes accompagnent la
version chargée ; elles ne changent pas seulement parce qu’une nouvelle
version du code a été préparée. La publication dans le navigateur et celle
des programmes à télécharger peuvent avoir lieu à des dates différentes.
