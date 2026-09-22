+++
title = "Télécharger le PDF individuel d’un carnet"
description = "Produire le fichier final d’un élève avec les options actuellement prévisualisées."
fiche = true
categorie = "carnets"
publics = ["responsable"]
intentions = ["carnet", "PDF", "télécharger", "imprimer", "élève", "fichier"]
prerequis = "Vous êtes responsable de la classe et avez relu le carnet de l’élève."
depart = "Prévisualisation du carnet → Télécharger le PDF"
statut = "disponible"
+++

## Étapes

1. Vérifier le contenu, le nombre de colonnes, le regroupement et les éléments
   complémentaires dans l’aperçu.
2. Sélectionner **Télécharger le PDF**.
3. Ouvrir le fichier obtenu et contrôler sa pagination avant diffusion.

Le bouton **Imprimer depuis le navigateur** constitue une autre sortie : il
ouvre la fonction d’impression du navigateur au lieu de générer le PDF côté
serveur.

## Résultat attendu

Le téléchargement porte un nom de la forme `carnet-prenom-nom.pdf`. La
génération reprend la couverture de l’école, les options visibles et les traces
autorisées. L’application journalise la génération et le téléchargement.

## Limites et précautions

- La génération est réservée au responsable ; l’enseignant associé peut relire
  l’aperçu mais ne voit pas ces actions.
- Le nom du fichier et son contenu comportent des données personnelles : le
  conserver et le transmettre comme un document scolaire confidentiel.
- Les photographies ne sont pas rendues publiques pour fabriquer le PDF. Le
  serveur les charge depuis le stockage privé au moyen d’une liste limitée aux
  médias du carnet en cours.
- La date d’édition correspond au jour de la génération.

Voir la [matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
