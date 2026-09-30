+++
title = "Prévisualiser le carnet d’un élève"
description = "Relire le carnet tel qu’il sera composé, sans créer de fichier ni modifier les observations."
fiche = true
categorie = "carnets"
publics = ["responsable", "associe"]
intentions = ["carnet", "prévisualiser", "aperçu", "relire", "élève"]
prerequis = "Vous pouvez consulter le suivi complet de l’élève."
depart = "Accueil → classe → élève → Voir le carnet"
statut = "disponible"
+++

## Étapes

1. Ouvrir la fiche de l’élève.
2. Sélectionner **Voir le carnet de…** en bas de la page.
3. Parcourir la couverture, les domaines, les acquisitions, les traces visibles
   et, selon les options, les bilans.
4. Essayer les choix de contenu et de mise en page pour contrôler le résultat.

{{< capture-guide src="captures/carnet.png" alt="Prévisualisation du carnet d’un élève fictif" caption="Aperçu produit automatiquement avec les seules données fictives de la démonstration." >}}

## Résultat attendu

L’aperçu reflète les paramètres habituels de l’école et les options choisies
pour cette consultation. Ces essais ne modifient ni les observations, ni les
paramètres enregistrés, ni le carnet d’un autre élève.

Les images des compétences et la photo de couverture reprennent les choix
de l’école, puis ceux de la classe lorsqu’elle a fait ses propres choix.
Les traces communes apparaissent avec le prénom de l’enfant lorsque le
commentaire utilise `<prenom>` ou `<prénom>`. Seule une compétence retenue
par les options de contenu peut montrer son image.

Voir [Choisir les images et les phrases proposées]({{< relref "/guide/carnets/personnaliser-presentation/" >}}).

## Limites et refus

- Responsable et enseignant associé peuvent prévisualiser le carnet.
- Seul le responsable voit les actions **Télécharger le PDF** et **Imprimer
  depuis le navigateur**.
- Un contributeur n’accède pas au carnet complet.
- Seules les traces et les bilans marqués comme visibles dans le carnet sont
  repris. Les éléments retirés en sont exclus, même s’ils restent conservés
  dans l’historique.

Voir les [règles détaillées des rôles]({{< relref "/roles/" >}}).

## Consulter une année du parcours

Dans **Année à consulter**, choisir une année proposée, ou **Parcours complet**.
Seules les années que vous êtes autorisé à consulter apparaissent. Le choix
reste conservé lorsque vous changez la mise en page ou téléchargez le PDF.

Une année précédente utilise les états d'apprentissage conservés pour cette
année. Une réussite enregistrée plus tard n'y est pas ajoutée. Si l'ancien état
n'a pas pu être retrouvé lors de la reprise des données, un message l'indique :
les traces conservées restent consultables, mais aucune réussite n'est inventée.
Pour voir ces traces, utiliser **Réussites et apprentissages en cours** ou
**Référentiel complet**.

La présentation d'une classe close garde ses derniers choix. Pour des données
plus anciennes, l'aperçu peut signaler qu'il reprend les choix disponibles lors
de la reprise, sans pouvoir retrouver les choix précédemment remplacés.
La clôture des choix n'a pas encore de bouton dans l'interface.

Ce parcours ne garantit pas une copie exacte d'un carnet déjà remis : les
commentaires, photographies et options d'édition peuvent avoir été corrigés.
