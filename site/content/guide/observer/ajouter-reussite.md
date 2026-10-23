+++
title = "Ajouter une réussite et un apprentissage libre"
description = "Créer un apprentissage pour un élève ou un groupe, avec ou sans référentiel."
fiche = true
categorie = "observer"
publics = ["responsable"]
intentions = ["réussite", "apprentissage", "libre", "groupe", "sans référentiel", "sous-domaine"]
prerequis = "Vous êtes responsable d’une classe active dont les choix sont ouverts."
depart = "Suivi d’un élève, ou Saisir pour toute la classe → catégorie → Ajouter une réussite"
statut = "disponible"
+++

## Saisir une réussite

1. Dans le suivi individuel ou collectif, ouvrir un domaine ou un sous-domaine,
   même vide, puis **Ajouter une réussite**.
2. Décrire l’**Apprentissage**, vérifier le domaine et le sous-domaine facultatif.
   Choisir le repère de section pour le retrouver avec les filtres habituels.
3. Sélectionner uniquement les **Élèves concernés** et la **Date de la réussite**.
   Le commentaire et la photo de réalisation sont facultatifs.
4. Cliquer sur **Enregistrer la réussite**.

L’apprentissage possède une identité durable ; une réussite est un événement
 daté de son suivi. L’état initial devient **Réussi**, puis reste modifiable
avec les commandes habituelles. Les traces suivantes complètent ce même
apprentissage. Une réussite passée reste datée dans le carnet selon les options
de visibilité, même si l’état courant redevient **En cours**.

{{< capture-guide src="captures/guide/observer/ajouter-reussite.png" alt="Formulaire fictif d’ajout d’une réussite" caption="Le libellé, la catégorie, les élèves et la date précèdent le commentaire et la photo facultatifs." >}}

## Partager et personnaliser

Plusieurs élèves partagent la même identité d’apprentissage, son libellé et
son classement. Leur état reste individuel. Leur première trace partage date,
commentaire et photo selon le [parcours des traces communes]({{< relref "/guide/observer/traces-communes" >}}).
**Personnaliser pour cet élève** détache la trace : ses modifications ne suivent
plus celles de la trace commune. Cela ne change ni l’identité ni le libellé de
l’apprentissage. Un libellé individuel différent n’est pas proposé.

Retirer un élève d’une trace commune retire cette attribution seulement. Ne plus
proposer un apprentissage à un élève ferme les prochaines saisies et conserve
son historique. Masquer une trace dans le carnet concerne sa diffusion seulement.

## Ajouter des élèves sans réussite

Depuis l’apprentissage dans le suivi collectif, ouvrir **Ajouter des élèves ou
ne plus proposer cet apprentissage**. Sélectionner les élèves puis **Ajouter au
suivi sans réussite**. Aucune ancienne réussite, trace ou photo ne leur est
attribuée. Pour fermer leurs prochaines saisies, utiliser **Ne plus proposer
aux élèves sélectionnés** ; les observations et carnets restent conservés.

Dans **Ajouter une réussite**, le dépliable **Retrouver un apprentissage déjà
créé** permet aussi sa reprise dans une classe gérée, notamment à la rentrée.
Elle demande un accès pédagogique à une classe qui l’utilisait ; aucun catalogue
public des apprentissages d’élèves n’est créé.

## Coexister avec un référentiel

Dans le collectif, **Apprentissage suivi pour … élèves** précise sa portée.
Les autres élèves sont **Hors du suivi**, sans être considérés comme en attente
de réussite. Ces apprentissages ne sont pas comptés dans les pourcentages du
référentiel commun. Ils restent distincts des compétences
[ajoutées pour une classe entière]({{< relref "/guide/eleves-classes/ajouter-competences" >}}).

Choisir ensuite une base conserve ces apprentissages et leurs traces. Changer
la base reste une opération avancée. Un libellé ressemblant à celui d’un
référentiel ne fusionne aucune identité et ne transfère aucune réussite.
Le libellé peut être reformulé pour le même apprentissage ; son classement est
conservé à la création. Décrire un autre apprentissage demande une nouvelle identité.

## Vérifier le carnet et les droits

Le carnet complet n’affiche pas les apprentissages libres des autres élèves.
La clôture conserve les définitions annuelles ; la reprise à la rentrée ne crée
pas de nouvel acquis. Les exports et imports conservent les rattachements et
les réussites datées ; un export de classe conserve son périmètre propre.

Seul le responsable crée une réussite ou change les élèves concernés. Les
associés et contributeurs gardent leurs droits habituels sur les traces ;
la direction seule n’accède pas au suivi pédagogique. Une classe close refuse
les nouvelles saisies et changements de portée.

Ces fonctions sont présentes dans le code du chantier Suivi libre. Vérifier
que la version de votre application les intègre.

{{< capture-guide src="captures/guide/observer/suivi-libre.png" alt="Apprentissages de la classe fictive des Cerfs-volants" caption="Le suivi collectif conserve les domaines et sous-domaines." >}}

{{< capture-guide src="captures/guide/observer/suivi-libre-mobile.png" alt="Suivi libre sur écran étroit" caption="Le même parcours sur un écran de téléphone." >}}
