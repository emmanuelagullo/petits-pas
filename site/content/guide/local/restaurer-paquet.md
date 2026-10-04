+++
title = "Restaurer ou transférer l’école sur cet appareil"
description = "Vérifier un ZIP, confirmer son contenu et redémarrer sur les données restaurées."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["restaurer", "récupérer", "sauvegarde", "ZIP", "redémarrer"]
prerequis = "Petits Pas fonctionne en mode local ; vous avez un ZIP de sauvegarde et la direction de l’école."
depart = "Gérer l’école → Sauvegardes locales → Restaurer une sauvegarde"
statut = "disponible"
+++

## Ce qui sera remplacé

La restauration remplace toute l’école présente sur cet appareil, y compris
les comptes, classes, observations et médias. Les saisies faites après la date
du ZIP ne sont pas fusionnées. Téléchargez d’abord un ZIP de l’état actuel et
conservez-le hors appareil. Après restauration, utilisez un compte du ZIP importé.

Pour un transfert, ouvrez une installation distincte avec une version compatible.
Après vérification, poursuivez les saisies sur une seule copie. Dans une version
qui propose ce parcours, vous pouvez d’abord [ouvrir une copie du ZIP sans
remplacer votre école]({{< relref "/guide/local/verifier-zip" >}}).

### Dans le navigateur

Choisissez le ZIP dans **Restaurer une sauvegarde**, cliquez sur **Vérifier la
sauvegarde**, puis lisez les détails. **Annuler** conserve l’école actuelle ;
**Confirmer la restauration** la remplace. Reconnectez-vous avec un compte importé.
L’état de récupération peut être ancien et reste sur le même appareil : il ne
remplace pas votre copie externe. Voir la [récupération navigateur]({{< relref "/guide/local/essayer-navigateur" >}}).

## Avec le programme : vérifier, confirmer, redémarrer

Les étapes ci-dessous concernent le programme autonome. L’[application dans le navigateur]({{< relref "/guide/local/essayer-navigateur.md" >}})
utilise le même ZIP avec une confirmation et une reconnexion, sans ce redémarrage.
La direction ne
peut pas remplacer depuis son navigateur la base d’une installation hébergée
partagée. Voir la [comparaison des façons de travailler]({{< relref "/guide/local/" >}}).

1. Sélectionnez l’archive ZIP et cliquez sur **Vérifier la sauvegarde**.
   L’application présente sa date et le nombre de médias après vérification.
   Le paquet actuel n’est pas encore remplacé.
2. Si vous souhaitez aussi conserver l’état actuel sous forme de ZIP, cliquez
   sur **Télécharger un ZIP du paquet actuel** et gardez ce fichier en lieu sûr.
3. Cliquez sur **Confirmer la restauration** après avoir vérifié la date et le
   dossier indiqué. Les modifications sont alors bloquées.
4. Cliquez sur **Appliquer la restauration et redémarrer**. La fenêtre se ferme,
   l’application restaure le paquet et se relance. En cas d’ouverture dans un
   navigateur externe, fermez la fenêtre et relancez Petits Pas manuellement.

Le message **Restauration terminée** indique la date de la sauvegarde et le
chemin où l’ancien paquet a été conservé. Celui-ci contient la base, les médias
et la clé précédents : c’est un dossier, **pas** un ZIP. L’archive choisie pour
la restauration reste distincte du paquet restauré ; conservez-en votre copie
dans un lieu sûr. Le retour à une ancienne version du **programme** est une
opération différente, décrite dans la [fiche d’installation]({{< relref "/guide/local/installer-programme.md" >}}).
