+++
title = "Générer les carnets PDF d’une classe"
description = "Créer une archive ZIP contenant un PDF distinct pour chaque élève sélectionné."
fiche = true
categorie = "carnets"
publics = ["responsable"]
intentions = ["carnets", "classe", "PDF", "ZIP", "archive", "télécharger", "élèves"]
prerequis = "Vous êtes responsable de la classe et les carnets concernés ont été relus."
depart = "Accueil → classe → Préparer les carnets PDF"
statut = "disponible"
+++

## Étapes

1. Ouvrir la classe et sélectionner **Préparer les carnets PDF**.
2. Cocher les élèves concernés, ou **Sélectionner toute la classe**.
3. Choisir les apprentissages, le regroupement, le nombre de colonnes et les
   éléments complémentaires.
4. Sélectionner **Télécharger l’archive ZIP**.
5. Décompresser l’archive et contrôler quelques fichiers avant diffusion.

## Résultat attendu

Le fichier `carnets-nom-de-la-classe.zip` contient un PDF par élève. Chaque PDF
porte un nom dérivé de l’identité affichée ; si deux noms produisent le même nom
de fichier, un numéro est ajouté pour éviter l’écrasement. La génération et le
téléchargement de l’archive sont journalisés.

## Limites, refus et précautions

- Il faut sélectionner au moins un élève. Sinon, la page reste affichée avec le
  message **Sélectionnez au moins un enfant.**
- Seul le responsable de la classe accède à cette page et peut générer
  l’archive.
- Les options de ce formulaire s’appliquent à tous les élèves sélectionnés et
  remplacent les valeurs habituelles pour cette seule édition.
- L’archive et les noms de ses fichiers contiennent des données personnelles.
  Ils doivent être conservés et transmis comme des documents scolaires
  confidentiels.

Pour contrôler un élève avant la génération collective, utiliser
[Prévisualiser le carnet d’un élève]({{< relref "previsualiser-carnet.md" >}}).
