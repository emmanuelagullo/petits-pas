+++
title = "Inventaire des tâches"
description = "Fonctions accessibles, publics concernés et limites actuelles de l’interface."
+++

Cet inventaire est établi à partir des vues, formulaires, autorisations, tests
et scénarios de démonstration. La première série comptait 31 fiches ; le guide
couvre maintenant 34 fiches dans six rubriques. Il prend comme référence l’interface et
les tests après la consolidation initiale de l’authentification (#C2 à #C4),
ainsi que les scénarios documentaires jusqu’à #G8.

Les statuts employés sont :

- **disponible** : le parcours peut être accompli dans l’interface ;
- **partiel** : une étape ou une variante importante reste à expliquer ou à
  compléter ;
- **interne** : la règle ou le service existe, sans parcours utilisateur ;
- **absent** : aucune fonction correspondante n’est actuellement proposée.

## Accéder à Petits Pas

| Je voudrais… | Pour qui ? | État | Point important |
| --- | --- | --- | --- |
| Me connecter et revenir à la page demandée | Toute personne autorisée | Disponible | Le compte doit posséder une responsabilité ou une affectation active. |
| Créer mon compte depuis une invitation | Personne invitée | Disponible | Le mot de passe doit satisfaire les contrôles de sécurité affichés. |
| Rattacher mon compte existant à une école | Personne invitée | Disponible | L’adresse du compte doit correspondre à l’invitation. |
| Réinitialiser mon mot de passe | Toute personne disposant d’un compte | Selon l’installation | Nécessite l’envoi de courriel ; la réponse ne révèle pas si l’adresse est connue. |
| Réutiliser un lien accepté, révoqué ou expiré | — | Refusé | Une nouvelle invitation doit être créée. |
| Choisir entre plusieurs écoles | Personne rattachée à plusieurs écoles | Absent | Le contexte d’école est actuellement choisi automatiquement. |

## Observer les apprentissages

| Je voudrais… | Responsable | Associé | Contributeur | Direction seule |
| --- | ---: | ---: | ---: | ---: |
| Voir les élèves d’une classe | Oui | Oui | Vue minimale | Vue administrative |
| Consulter le suivi complet d’un élève | Oui | Oui | Non | Non |
| Filtrer le suivi par niveau ou sur tout le cycle | Oui | Oui | Non | Non |
| Modifier l’état d’une acquisition | Oui | Non | Non | Non |
| Choisir une compétence pour toute la classe | Oui | Oui | Non | Non |
| Consulter une grille de suivi | Oui | Oui | Non | Non |
| Télécharger la grille en PDF | Oui | Non | Non | Non |

## Ajouter et gérer des traces

| Je voudrais… | État | Limite importante |
| --- | --- | --- |
| Ajouter un commentaire ou une photographie | Disponible | Une affectation active autorisant la contribution est nécessaire. |
| Utiliser une formulation proposée | Disponible | Le texte reste modifiable avant enregistrement. |
| Modifier ma propre trace | Disponible | Seulement pendant une affectation active dans la classe. |
| Modifier une trace d’une autre personne | Responsable seulement | L’auteur et le dernier éditeur restent distingués. |
| Masquer ou réafficher une trace dans le carnet | Disponible selon le rôle | Le contenu reste conservé. |
| Retirer une trace | Disponible | Il s’agit d’une suppression logique. |
| Restaurer une trace retirée | Responsable seulement | Seulement dans la scolarité courante. |
| Voir une photographie | Disponible selon le périmètre | Les médias restent privés et contrôlés par le serveur. |
| Télécharger l’original d’une photographie | Responsable ou auteur autorisé | Le téléchargement significatif est audité. |

## Bilans et carnets

| Je voudrais… | État | Public ou limite |
| --- | --- | --- |
| Ajouter quelques mots sur le parcours | Disponible | Responsable de la classe. |
| Modifier, masquer ou retirer un bilan | Disponible | Responsable ; un seul bilan par date et scolarité. |
| Prévisualiser un carnet | Disponible | Responsable ou enseignant associé. |
| Choisir réussites, observations ou référentiel complet | Disponible | Options de prévisualisation et de génération. |
| Regrouper par année, mois ou bilan | Disponible | Le regroupement « aucun » est également proposé. |
| Utiliser une ou deux colonnes | Disponible | Valeur habituelle définissable par la direction. |
| Afficher attendus, sous-domaines et bilans | Disponible | Chaque option peut être activée séparément. |
| Télécharger le PDF individuel | Disponible | Responsable seulement. |
| Générer les carnets d’une classe dans une archive ZIP | Disponible | Responsable ; au moins un élève doit être sélectionné. |
| Définir les paramètres habituels des carnets | Disponible | Direction. |

## Classes et élèves

| Je voudrais… | État | Public ou limite |
| --- | --- | --- |
| Créer une classe pour une année scolaire | Disponible | Direction ; la classe commence « en préparation ». |
| Attribuer un responsable puis activer la classe | Disponible | Direction ; activation impossible sans responsable actif. |
| Renommer une classe | Absent | Aucun formulaire actuellement. |
| Archiver ou supprimer une classe | Absent | Le modèle prévoit un état archivé, sans parcours d’interface. |
| Coller une liste de nouveaux élèves | Disponible | Responsable ou direction selon le périmètre. |
| Ajouter un élève déjà connu | Disponible | Direction. |
| Modifier le niveau d’un élève | Disponible | Responsable de la classe ou direction selon le contexte. |
| Corriger le prénom, le nom ou l’année de naissance | Disponible | Responsable autorisé ou direction. |
| Déplacer un élève dans une autre classe | Disponible | Direction et confirmation explicite. |
| Retirer un élève de la classe | Disponible sous condition | Refus si des traces ou bilans sont rattachés à cette scolarité. |
| Retirer puis archiver sans supprimer le parcours | Disponible | Le parcours antérieur est conservé. |
| Réactiver un élève archivé | Disponible | Une nouvelle scolarité peut ensuite être nécessaire. |
| Préparer une nouvelle année scolaire | Disponible | Direction ; les années précédentes sont conservées. |
| Rechercher les élèves par année, niveau ou état | Disponible | Annuaire réservé à la direction. |
| Valider un rapprochement avec un dossier existant | Disponible | La direction décide ; aucune fusion automatique des homonymes. |

## Équipe et gouvernance

| Je voudrais… | État | Public ou limite |
| --- | --- | --- |
| Voir les membres et leurs coordonnées | Disponible | Direction. |
| Voir les collaborateurs d’une classe | Disponible | Personnes affectées ; coordonnées non affichées. |
| Inviter une nouvelle personne | Disponible | Direction ; courriel automatique si configuré, sinon lien à transmettre manuellement, affiché une seule fois. |
| Révoquer une invitation encore valable | Disponible | Direction. |
| Attribuer une fonction de classe | Disponible | Responsable, enseignant associé ou contributeur. |
| Limiter une affectation dans le temps | Disponible | Date de fin facultative et motif conservé. |
| Remplacer le responsable d’une classe | Disponible | Création et retrait sont réalisés dans une même transaction. |
| Terminer une affectation | Disponible | Le dernier responsable doit d’abord être remplacé. |
| Suspendre une affectation en urgence | Disponible | Motif obligatoire ; une anomalie peut être ouverte. |
| Attribuer ou retirer une responsabilité de direction | Interne | Services présents, sans interface publique. |

## Utiliser le mode local sur un ordinateur

| Je voudrais… | État | Point important |
| --- | --- | --- |
| Installer ou mettre à jour le programme | Prototype | Archives distinctes pour Ubuntu et Windows ; les données restent dans un dossier séparé. |
| Revenir à la version précédente du programme | Disponible après installation | Fermer l’application ; une migration de la base peut empêcher une ancienne version de la relire. |
| Télécharger un ZIP du paquet local | Disponible en mode local | Direction ; conserve la base, les médias et la clé du paquet. |
| Restaurer un ZIP du paquet local | Disponible en mode local | Direction ; après vérification et confirmation, l’application redémarre et l’ancien paquet reste dans un dossier séparé. |

Ce mode fonctionne sur un seul ordinateur, sans serveur distant et sans
collaboration entre postes. Les [fiches du mode local]({{< relref "/guide/local/" >}})
décrivent les manipulations. Le déploiement serveur garde ses propres procédures
de sauvegarde et de reprise.

## Fonctions d’exploitation hors du guide quotidien

Les opérations suivantes existent mais relèvent aujourd’hui des commandes ou
de l’exploitation, et non d’un parcours utilisateur ordinaire :

- créer une école et attribuer une direction de secours ;
- charger ou actualiser le référentiel de compétences ;
- diagnostiquer le déploiement et le stockage objet ;
- sauvegarder et restaurer PostgreSQL et les médias ;
- initialiser ou réinitialiser un atelier pédagogique fictif.

Elles restent documentées dans les rubriques [DSI]({{< relref "/dsi/" >}}) et
[Conception]({{< relref "/conception/" >}}), sans être mélangées aux gestes
quotidiens des équipes pédagogiques.

## Bilan de couverture

Les captures reproductibles existantes couvrent déjà la connexion, une classe,
les acquisitions, un carnet, la gestion de l’école, les collaborateurs, les
fonctions de l’équipe, les invitations et plusieurs différences de périmètre.

Les formulaires qui apportent une information nouvelle sont désormais couverts
par des cadrages ciblés : création d’une classe, composition d’une classe, trace
avec photographie, bilan, préparation des PDF et remplacement d’un responsable.
Ils sont déclarés dans la configuration YAML fictive commune et rejoués par le
même scénario Playwright que les captures des rôles. Une capture n’est pas
ajoutée lorsqu’un court texte suffit.

Le contrôle automatique du guide vérifie désormais, avant les captures en CI :

- les métadonnées nécessaires à la recherche par intention et aux entrées par
  rôle ;
- l’existence des cibles de liens internes et des renvois vers la documentation
  détaillée des autorisations ;
- la déclaration YAML de chaque capture utilisée et l’utilisation effective de
  chaque capture propre au guide ;
- la présence d’un texte alternatif et d’une légende pour chaque illustration.

Hugo conserve en complément son contrôle strict de construction, puis
Playwright régénère les images et le vérificateur d’images contrôle inventaire,
dimensions et budget total.

## Écarts restant ouverts

Le guide ne présente pas comme disponibles les parcours que l’interface ne
propose pas encore : choix entre plusieurs écoles, renommage et archivage d’une
classe, ou attribution d’une responsabilité de direction. La création d’une
trace vide reste techniquement acceptée et est signalée dans la fiche
concernée. Les opérations d’exploitation restent séparées des gestes
quotidiens.

La reprise #G6b est volontairement différée : elle réexaminera les fiches
d’invitation, de compte et d’affectation après les évolutions ultérieures de la
phase d’authentification, sans bloquer le présent guide.
