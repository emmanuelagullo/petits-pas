+++
title = "Situations et parcours"
description = "Comprendre les cumuls de fonctions, les périodes, les invitations et les refus significatifs."
+++

Les autorisations de Petits Pas répondent à une situation précise : **qui agit,
sur quelle ressource, dans quelle école ou classe, et à quelle date ?** Les
mêmes mots — enseigner, contribuer, remplacer — peuvent donc conduire à des
écrans différents selon le contexte.

Les captures sont recréées automatiquement avec l'application et les comptes
fictifs. Elles montrent les actions proposées aujourd'hui ; l'absence d'un
bouton ne remplace jamais le contrôle effectué par le serveur.

## Partager une classe

Rémi et Nadia sont tous deux responsables des Coccinelles. Ils disposent dans
cette classe des mêmes capacités pédagogiques : consulter et modifier le
suivi, relire les contributions, préparer les carnets et générer les PDF.
Nadia est également responsable des Papillons. Cette seconde affectation
étend son périmètre à cette classe, mais ne lui attribue aucun droit de
direction sur l'école.

{{< scenarios-demonstration ids="nadia-collaborateurs" >}}

## Contribuer sans consulter tout le suivi

Cora intervient comme ATSEM contributrice chez les Coccinelles. Elle peut
ajouter une observation à un élève, mais ne consulte ni le suivi pédagogique
complet ni les contributions des autres membres. L'écran lui donne uniquement
les informations et l'action nécessaires à cette contribution.

{{< scenarios-demonstration ids="cora-contribution" >}}

## Changer de fonction selon la classe

Samir est contributeur chez les Coccinelles et enseignant associé chez les
Papillons. Chez les Coccinelles, il voit seulement l'identité minimale des
élèves nécessaire à une contribution. Chez les Papillons, il consulte le suivi
complet et peut ajouter des traces. Les droits reçus dans une classe ne se
propagent jamais à l'autre.

{{< scenarios-demonstration ids="samir-coccinelles,samir-papillons" >}}

## Remplacer pour une période limitée

Léa est responsable temporaire des Papillons. Pendant son remplacement, elle
dispose des droits pédagogiques correspondants. La date de fin est enregistrée
dès l'affectation et les autorisations sont recalculées à chaque requête : une
page ouverte auparavant ne permet pas de continuer à agir après l'échéance.

Alice illustre la situation après la fin d'une intervention. Ses anciennes
contributions restent conservées et attribuées à son identité, mais elle ne
peut plus rouvrir la classe ni les modifier. Historique et autorisation
présente sont ainsi deux notions distinctes.

{{< scenarios-demonstration ids="lea-remplacement,alice-affectation-terminee" >}}

## Appartenir à l'école sans être affecté

Marc possède un compte et une appartenance active à Ma Belle École, mais aucune
responsabilité ni affectation. Cette appartenance ne lui ouvre aucune classe et
ne suffit pas à entrer dans l'application. Elle permet de préparer une future
fonction sans accorder de droits par anticipation.

{{< scenarios-demonstration ids="marc-sans-affectation" >}}

## Inviter une personne

La direction peut créer une invitation liée à une adresse électronique, puis
la révoquer tant qu'elle n'a pas été utilisée. Le jeton n'est pas conservé en
clair. Lors de l'acceptation, l'adresse du compte, l'état, l'échéance et le
jeton sont vérifiés avant de créer l'appartenance.

La démonstration contient une invitation en attente et une invitation révoquée.
Leurs adresses utilisent le domaine réservé `example.test` et les jetons
fictifs publiés ne permettent aucune invitation réelle.

{{< scenarios-demonstration ids="invitations" >}}

## Refuser sans dévoiler

Un refus n'est pas toujours montré par une grande page « accès interdit » :

- une action non autorisée n'est pas proposée dans l'interface ;
- un identifiant appartenant à une autre école ou à une classe inaccessible
  est généralement traité comme une ressource introuvable ;
- une requête forgée est contrôlée par les mêmes règles que la navigation ;
- une action groupée est refusée avant toute modification si l'un de ses objets
  sort du périmètre autorisé ;
- une tentative significative d'accès inter-écoles ou d'élévation de privilège
  est destinée à être auditée sans recopier le contenu sensible.

Ces choix réduisent les informations révélées à une personne qui essaierait de
deviner une adresse ou un identifiant.

{{< scenarios-demonstration ids="direction-classe-sans-suivi" >}}

## Procédures de secours

La direction ne reçoit pas silencieusement les droits pédagogiques. Si elle
doit exceptionnellement intervenir dans une classe, une affectation temporaire
avec motif et date de fin est nécessaire et fait l'objet d'un audit distinct.

En cas d'urgence, la direction peut suspendre une affectation, y compris celle
du dernier responsable. La classe n'est pas présentée comme normalement gérée
pour autant : une anomalie de gouvernance signale alors qu'un nouveau
responsable doit être désigné. La classe fictive des Lucioles illustre une
classe en préparation qui ne peut être activée avant cette désignation.

{{< scenarios-demonstration ids="gouvernance-secours" >}}

Pour les règles normatives et leurs tests associés, consultez la [matrice des
autorisations]({{< relref "/conception/documents/matrice-autorisations.org" >}}).
