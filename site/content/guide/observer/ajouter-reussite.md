+++
title = "Ajouter une compétence et suivre ses réussites"
description = "Créer une compétence pour un élève ou un groupe, avec ou sans référentiel."
fiche = true
categorie = "observer"
publics = ["responsable"]
intentions = ["réussite", "apprentissage", "libre", "groupe", "sans référentiel", "sous-domaine"]
prerequis = "Vous êtes responsable d’une classe active dont les choix sont ouverts."
depart = "Suivi d’un élève, ou Saisir pour toute la classe → catégorie → Ajouter une compétence"
statut = "disponible"
+++

## Créer une compétence et commencer son suivi

1. Dans une catégorie, même vide, choisir **Ajouter une compétence** depuis
   le collectif, ou **Ajouter une compétence et une réussite** depuis un élève.
2. Saisir la **Description de la compétence**. Les exemples et **Retrouver une
   compétence déjà créée** aident à éviter les copies inutiles.
3. Vérifier domaine, sous-domaine facultatif, section et élèves concernés.
4. Dans l’encadré **Réussite — facultatif**, choisir **Enregistrer également une réussite** si le constat est déjà fait,
   pour placer la compétence à l’état **Réussi**. Cette option est présélectionnée
   depuis un élève et décochée depuis le collectif. Elle ne commande ni la trace
   ni l’illustration. Renseigner la **Date du constat** si vous enregistrez une
   réussite ou une trace ; la date n’est pas nécessaire pour ouvrir le suivi seul.
5. Au besoin, ouvrir **Ajouter une trace — facultatif** pour un commentaire
   et/ou une photo. Une trace seule ne valide pas la compétence.
6. Au besoin, ouvrir **Illustration de la compétence — facultatif** pour choisir
   une icône. Cette illustration commune reste distincte des photos des traces.
   Ensuite, cliquer sur l’illustration ou **Modifier l’illustration** dans la page
   de compétence permet de la changer ou d’importer une image pour cette classe.
7. Cliquer sur **Enregistrer**. La page habituelle de compétence permet ensuite
   de modifier les états, d’ajouter des traces et de régler le suivi par élève.

La compétence possède une identité durable. Une réussite est un événement daté ;
l’état courant **Réussi** reste modifiable. Une réussite passée et ses traces
ne sont pas effacées lorsque l’état redevient **En cours**.

{{< capture-guide src="captures/guide/observer/ajouter-reussite.png" alt="Formulaire fictif de création d’une compétence" caption="La réussite est optionnelle ; la trace et l’illustration disposent de dépliables indépendants." >}}

## Partager et personnaliser

Plusieurs élèves partagent la même identité de compétence, son libellé et
son classement. Leur état reste individuel. Si une trace est enregistrée pour le groupe, elle partage date,
commentaire et photo selon le [parcours des traces communes]({{< relref "/guide/observer/traces-communes" >}}).
**Personnaliser pour cet élève** détache la trace : ses modifications ne suivent
plus celles de la trace commune. Cela ne change ni l’identité ni le libellé de
la compétence. Un libellé individuel différent n’est pas proposé.

Retirer un élève d’une trace commune retire cette attribution seulement.
Désactiver son suivi ferme les prochaines saisies et conserve l’historique.
Masquer une trace dans le carnet concerne sa diffusion seulement.

## Activer ou désactiver le suivi

La page habituelle de compétence affiche **Activer le suivi** pour un élève
hors du suivi et **Désactiver le suivi** pour un élève déjà concerné.
L’activation n’attribue aucune réussite, trace ni photo. La réactivation retrouve
les observations conservées, sans nouvelle réussite automatique. Désactiver le
suivi retire la compétence du compteur actif de cet élève sans effacer son parcours.

Le dépliable **Retrouver une compétence déjà créée**, près de sa description,
permet aussi de reprendre une compétence dans une nouvelle classe ou année.
Cette reprise exige un accès pédagogique à un usage antérieur ; elle ouvre
le suivi des élèves sélectionnés sans recopier leurs anciennes réussites.

## Corriger la date d’une réussite

Le clic rapide reste inchangé : il utilise aujourd’hui. Ouvrir ensuite
**Réussi · date**, ou **Date de la réussite**, permet de choisir **Aujourd’hui**,
de conserver la précédente réussite ou de choisir librement une date de l’année.
La précédente date est proposée après une revalidation : utilisez-la si la
dévalidation était accidentelle. Un nouveau constat peut garder aujourd’hui.
Ce choix ne modifie aucune date de trace. Les années closes restent consultables.

## Coexister avec un référentiel

Dans le collectif, **Compétence suivie pour … élèves** précise sa portée.
Les autres élèves sont **Hors du suivi**, sans être considérés comme en attente
de réussite. Chaque compteur d’élève inclut les compétences communes et ses compétences
ciblées dont le suivi est actif, selon le filtre de section choisi. Une compétence
ciblée ne compte jamais pour les élèves hors de son suivi. Dans une classe sans
compétence prédéfinie, Ana affiche ainsi **1/1** pour sa seule compétence réussie,
ou **0/1** si elle n’est pas réussie ; un autre élève hors de ce suivi reste à
**0/0**. Ces compétences restent distinctes des compétences
[ajoutées pour une classe entière]({{< relref "/guide/eleves-classes/ajouter-competences" >}}).

Choisir ensuite une base conserve ces compétences et leurs traces. Changer
la base reste une opération avancée. Un libellé ressemblant à celui d’un
référentiel ne fusionne aucune identité et ne transfère aucune réussite.
Le libellé peut être reformulé pour la même compétence ; son classement est
conservé à la création. Décrire une autre compétence demande une nouvelle identité.

## Vérifier le carnet et les droits

Le carnet complet n’affiche pas les compétences ciblées des autres élèves.
La clôture conserve les définitions annuelles ; la reprise à la rentrée ne crée
pas de nouvel acquis. Les exports et imports conservent les rattachements et
les réussites datées ; un export de classe conserve son périmètre propre.

Seul le responsable crée une réussite ou change les élèves concernés. Les
associés et contributeurs gardent leurs droits habituels sur les traces ;
la direction seule n’accède pas au suivi pédagogique. Une classe close refuse
les nouvelles saisies et changements de portée.

Ces fonctions sont présentes dans le code du chantier Suivi libre. Vérifier
que la version de votre application les intègre.

{{< capture-guide src="captures/guide/observer/suivi-libre.png" alt="Compétences de la classe fictive des Cerfs-volants" caption="Le suivi collectif conserve les domaines et sous-domaines." >}}

{{< capture-guide src="captures/guide/observer/suivi-libre-mobile.png" alt="Suivi libre sur écran étroit" caption="Le même parcours sur un écran de téléphone." >}}
