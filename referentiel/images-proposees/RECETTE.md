# Comparer les illustrations et les photos — données fictives

Depuis les sources et leurs dépendances installées :

```sh
python scripts/recetter-images-proposees.py --destination /tmp/carnets-images-fictifs
```

Choisir un dossier qui n'existe pas. Le script utilise sa propre base temporaire,
au courrier désactivé ; il ne lit ni ne modifie les données d'une école existante.
Ouvrir `index.html` dans le dossier produit. Les aperçus HTML et PDF sont autonomes.
Les dessins de pots servent uniquement de photographies synthétiques de réalisations.

| Élève fictif | Photos dans les traces affichées | Cacher l'image lorsqu'une photo est affichée | Garder aussi l'image |
| --- | --- | --- | --- |
| Alix | Aucune | Image proposée | Image proposée |
| Lou | Une collective et une personnelle, dans deux traces | Les deux photos | Les deux photos et l'image |
| Noé | Version personnelle avec photo remplacée | Sa photo | Sa photo et l'image |
| Inès | Version personnelle dont la photo a été retirée | Image proposée | Image proposée |

La personnalisation d'une trace commune conserve son fonctionnement habituel :
une version personnelle devient indépendante. Elle ne réaffiche pas la photo
commune qu'elle a remplacée. Lou montre le cas de deux photos effectivement
présentes, qu'il faut conserver toutes les deux.

Comparer les deux PDF de Lou pour vérifier qu'aucune photo ne disparaît.
Dans les carnets avec illustration, vérifier la petite mention OpenMoji unique
et les liens de crédit. Les illustrations n'attestent aucune réussite.

Pour essayer l'interface dans une démonstration fictive, ouvrir **Présentation
du carnet → Images proposées et photos**, changer le choix, enregistrer, puis
rouvrir le carnet et télécharger le PDF. À l'école, la direction prépare le
défaut ; dans la classe, son responsable peut le garder ou faire un autre choix.

Pour vérifier aussi les associations des trois éditions fournies :

```sh
python scripts/recetter-images-proposees.py --avec-associations --destination /tmp/carnets-associations-fictifs
```

Le script ajoute trois carnets de Camille Fictif, avec cinq apprentissages de
chaque source : récit, écriture, course, rythme et comparaison de masses. Il
importe et adopte les vraies éditions dans sa seule base temporaire. Vérifier
les cinq illustrations, leurs textes et le crédit OpenMoji unique en fin de
carnet. Il n’importe aucune photographie réelle.
