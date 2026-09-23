+++
title = "Comprendre une action absente ou une page introuvable"
description = "Distinguer un droit manquant, un périmètre différent, une période terminée et une fonction non disponible."
fiche = true
categorie = "depannage"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["bouton absent", "action absente", "page introuvable", "404", "accès refusé", "permission", "droit"]
prerequis = "Vous êtes connecté et savez dans quelle école et quelle classe l’action était attendue."
depart = "La page ou l’action qui ne correspond pas à votre attente"
statut = "disponible"
+++

## Commencer par le symptôme

| Symptôme | Cause probable | Vérification utile |
| --- | --- | --- |
| Le bouton n’apparaît pas | L’interface masque une action que votre fonction ne permet pas | Comparer votre fonction et la classe avec la page **Collaborateurs** |
| Une ancienne adresse devient introuvable | L’objet est hors de votre périmètre, archivé, retiré, ou votre affectation a pris fin | Revenir par l’accueil plutôt que réutiliser l’adresse |
| La page s’ouvre mais l’envoi est refusé | Lire ou prévisualiser est permis, modifier ou générer ne l’est pas | Vérifier l’action précise dans la matrice |
| Une ressource d’une autre école est introuvable | La séparation entre écoles est appliquée | Vérifier l’école courante et ne pas modifier l’adresse manuellement |
| `POST attendu` | Une action de modification a été appelée comme une simple page | Reprendre le bouton ou le formulaire prévu |

## Pourquoi « introuvable » plutôt que « interdit » ?

Pour les élèves, médias et classes hors périmètre, Petits Pas répond souvent
comme si la ressource n’existait pas. Ce choix évite de confirmer à une personne
non autorisée qu’un dossier ou une photographie existe réellement.

Il ne faut donc pas déduire d’une page introuvable que les données ont été
supprimées.

## Vérifications dans l’ordre

1. Revenir à l’accueil et ouvrir la classe depuis la liste proposée.
2. Vérifier la fonction, la période et l’état de l’affectation dans
   **Collaborateurs**, ou demander cette vérification à la direction.
3. Vérifier que la classe est active et que l’élève n’est pas archivé.
4. Distinguer consultation, contribution, changement d’état et génération :
   ces actions n’utilisent pas le même droit.
5. Si le refus paraît incohérent, conserver le message et le chemin suivi, sans
   transmettre de photographie ni de donnée d’élève dans un canal public.

## Ce qui n’est pas une panne

- La direction n’accède pas automatiquement au suivi pédagogique.
- Un associé prévisualise un carnet mais ne génère pas le PDF.
- Un contributeur ajoute ses propres traces sans voir le dossier complet.
- Une affectation terminée ou arrivée à sa date de fin ne conserve pas les
  droits, même si ses contributions restent attribuées.

Voir la [présentation des rôles]({{< relref "/roles/" >}}), les
[situations illustrées]({{< relref "/roles/situations/" >}}) et la
[matrice normative]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
