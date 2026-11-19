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
2. Sous **Compétences à afficher**, choisir le cycle entier ou une section,
   puis la compétence observée. Le choix de section filtre les compétences.
   La liste des élèves de la compétence conserve le même périmètre.
3. Pour chaque élève concerné, sélectionner sa ligne : **réussi**, **en cours**,
   puis **pas encore observé** se succèdent.
4. Utiliser **Saisir pour toute la classe** dans le fil d’Ariane pour retrouver
   la liste des compétences avec la section choisie.

### Ajouter des traces individuelles

Ouvrir le **+** de l’élève dans la liste de la compétence. **Enregistrer la trace**
revient à sa ligne. **Enregistrer et passer à l’élève suivant** ouvre directement
la trace suivante après l’enregistrement. Au-dessus du formulaire, **Élève
précédent** et **Élève suivant** permettent de relire les traces dans l’ordre de
la liste. Le fil d’Ariane ramène à la liste si vous souhaitez choisir un autre
élève.

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

## Compétences de certains élèves

**Ajouter une compétence hors référentiel** est indépendant des compétences existantes. Une compétence ciblée indique le nombre d’élèves suivis ; les autres restent **Hors du suivi**. Sa répartition porte seulement sur les élèves encore concernés.

**Sélectionner toute la classe** coche toutes les cases proposées. Vérifiez le
nombre d’élèves sélectionnés et l’option **Enregistrer une réussite** avant de
valider.

Voir [le suivi libre et ses règles]({{< relref "/guide/observer/ajouter-reussite" >}}).

## Date du constat

Le clic rapide utilise aujourd’hui. La commande **Réussi · date** ou **Date de
la réussite**, sur chaque ligne d’élève, permet de conserver la précédente
réussite ou de choisir une date de l’année scolaire. Les dates des traces
restent indépendantes. Voir [corriger une date de réussite]({{< relref "/guide/observer/mettre-a-jour-acquisition" >}}).
