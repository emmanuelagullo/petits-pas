+++
title = "Ajouter quelques mots sur le parcours d’un élève"
description = "Créer un bilan daté, le corriger et décider de son inclusion dans le carnet."
fiche = true
categorie = "observer"
publics = ["responsable", "associe"]
intentions = ["bilan", "parcours", "texte", "carnet", "élève", "visibilité"]
prerequis = "Vous pouvez consulter l’élève. La création et les modifications sont réservées au responsable de sa classe courante."
depart = "Fiche de l’élève → Quelques mots sur son parcours"
statut = "disponible"
+++

## Ajouter un bilan

1. Ouvrir **Quelques mots sur son parcours**.
2. Vérifier l’année scolaire proposée — seule la scolarité courante est
   disponible pour une nouvelle saisie.
3. Choisir la date et saisir le texte.
4. Choisir si le bilan doit apparaître dans le carnet.
5. Sélectionner **Ajouter le bilan**.

{{< capture-guide src="captures/guide/observer/bilan.png" alt="Formulaire d’ajout de quelques mots sur le parcours d’un élève fictif" caption="Année, date, texte et visibilité dans le carnet sont regroupés dans un même formulaire." >}}

## Modifier, masquer ou retirer

Le responsable peut ensuite modifier le bilan courant, basculer entre
**Affiché dans le carnet** et **Masqué du carnet**, ou sélectionner **Retirer ce
bilan** puis confirmer. Le retrait est logique : les données ne sont pas
effacées physiquement.

## Résultat attendu

Le bilan rejoint la liste chronologique avec sa date, son niveau et son année
scolaire. S’il est visible et si l’option d’inclusion des bilans est active, il
peut être repris lors de la génération du carnet.

## Limites et refus

- Il ne peut exister qu’un bilan par élève et par date pour une même scolarité.
  En cas de doublon, le formulaire est refusé et le texte saisi reste affiché
  pour permettre la correction.
- L’enseignant associé peut lire les bilans auxquels son accès donne droit,
  mais il ne peut ni en créer ni les modifier.
- Les bilans d’une ancienne scolarité ne sont visibles que lorsque les règles
  de continuité du parcours l’autorisent ; ils restent non modifiables.

Voir les [situations illustrées de continuité et d’accès]({{< relref "/roles/situations/" >}})
et la [matrice des autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
