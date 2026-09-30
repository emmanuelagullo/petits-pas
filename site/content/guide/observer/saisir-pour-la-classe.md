+++
title = "Saisir une compétence pour toute la classe"
description = "Afficher tous les élèves pour mettre à jour rapidement une même compétence."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["classe", "compétence", "saisie groupée", "élèves", "acquisition"]
prerequis = "La classe est active et comporte des élèves. Seul le responsable peut changer les états."
depart = "Accueil → classe → Saisir pour toute la classe"
statut = "disponible"
+++

## Étapes

1. Ouvrir la classe et choisir **Saisir pour toute la classe**.
2. Sélectionner un domaine, puis la compétence observée.
3. Pour chaque élève concerné, sélectionner sa ligne : **réussi**, **en cours**,
   puis **pas encore observé** se succèdent.
4. Utiliser **Changer de compétence** pour poursuivre la séance sur un autre
   apprentissage.

## Résultat attendu

Dans le choix d'une compétence, une petite barre indique la répartition des
observations : réussites en vert, apprentissages en cours en orange, compétences
pas encore observées en gris. Le nombre de réussites est affiché sous la barre ;
les autres nombres apparaissent au survol ou lorsque le lien est sélectionné
au clavier. Les lecteurs d'écran disposent également des trois nombres.

Le total comprend les élèves non archivés inscrits dans cette classe pour son
année scolaire. Les états actuels sont les mêmes que dans la saisie : une
réussite conservée d'une année précédente compte aussi. Une absence
d'observation ne signifie pas que l'enfant ne maîtrise pas la compétence.

La page conserve la compétence en titre et présente une ligne par élève actif.
Chaque changement est enregistré immédiatement et apparaît aussi dans la fiche
individuelle de l’élève.

## Limites et refus

- L’enseignant associé peut consulter la saisie par classe et la grille, mais
  le changement d’état est réservé au responsable.
- La page signale explicitement une classe sans élève ; elle ne permet pas d’en
  inscrire un.
- Le responsable peut choisir **Ajouter ou modifier une trace commune** pour
  partager un commentaire et une photo avec les enfants sélectionnés. Un
  enseignant associé peut consulter les traces communes, mais ne les modifie
  pas pour toute la classe. Voir [Ajouter une trace commune]({{< relref "/guide/observer/traces-communes/" >}}).

La [matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}) distingue la
consultation du suivi de la modification des états.
