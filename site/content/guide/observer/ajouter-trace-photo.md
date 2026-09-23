+++
title = "Ajouter une observation ou une photo"
description = "Conserver une trace datée pour une compétence sans modifier son état d’acquisition."
fiche = true
categorie = "observer"
publics = ["responsable", "associe", "contributeur"]
intentions = ["observation", "trace", "commentaire", "photo", "date", "contribution"]
prerequis = "Vous contribuez actuellement dans la classe. Pour un contributeur, l’élève doit être actif dans cette classe."
depart = "Fiche de l’élève ou page Contribuer → bouton + d’une compétence"
statut = "disponible"
+++

## Étapes

1. Ouvrir l’élève, puis sélectionner le bouton **+** à droite de la compétence.
2. Saisir le mot qui accompagne la réussite, ou partir d’une proposition et
   l’adapter librement.
3. Vérifier la date de l’observation.
4. Ajouter, si utile, une photo du travail.
5. Si vous êtes responsable, laisser cochée ou décocher l’option **Afficher
   cette trace dans le carnet**.
6. Sélectionner **Ajouter la trace**.

{{< capture-guide src="captures/guide/observer/trace.png" alt="Formulaire d’ajout d’une trace avec commentaire, date et photographie" caption="Le cadrage montre uniquement les champs utiles, avec les données fictives de la démonstration." >}}

## Résultat attendu

La nouvelle trace rejoint l’historique daté de la compétence. Des indicateurs
signalent ensuite la présence d’un commentaire ou d’une photographie. Ajouter
une trace ne change jamais l’état **réussi**, **en cours** ou **pas encore
observé**.

## Limites et précautions

- Le formulaire accepte une trace composée d’un texte, d’une photo, ou des
  deux. L’interface ne bloque pas actuellement une trace vide : mieux vaut
  annuler plutôt que la conserver sans contenu.
- La taille maximale configurée pour une requête contenant une photo est de
  5 Mio ; un envoi plus volumineux est refusé.
- La photographie est servie par une route protégée ; son adresse de stockage
  n’est pas publique.
- Pour limiter les données personnelles, photographier le travail plutôt que
  le visage de l’enfant.
- Un enseignant associé ou un contributeur peut ajouter une trace mais ne
  décide pas si elle figurera dans le carnet.

Voir [Contribuer sans ouvrir tout le suivi]({{< relref "/roles/situations/" >}}#contribuer-sans-consulter-tout-le-suivi)
et les [règles d’accès aux médias]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
