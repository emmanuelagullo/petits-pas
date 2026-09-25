# Validation d'un paquet autonome (#L6)

Ce parcours vérifie **l'application distribuée**, pas seulement les tests
Python. Utiliser des données entièrement fictives et une image sans personne
identifiable. Noter la version, l'OS et le numéro de l'exécution GitHub Actions
dont provient l'archive. Tester Windows et Ubuntu séparément : le paquet Linux
issu d'Ubuntu 24.04 n'est pas validé sur Guix.

## 1. Préparer un paquet de test isolé

Décompresser intégralement `PetitsPas-windows.zip` ou
`PetitsPas-linux.tar.gz` ; conserver le dossier `PetitsPas` et son `_internal`.
Sur Ubuntu, installer GTK 3, WebKitGTK 4.1 et Pango si nécessaires.

Choisir un chemin **neuf** réservé à cet essai (le chemin des données est
indépendant du dossier de l'exécutable) :

```sh
# Ubuntu, depuis le dossier où l'archive a été extraite
./PetitsPas/PetitsPas --paquet "$HOME/petits-pas-essai-L6"
```

```powershell
# Windows PowerShell, depuis le dossier où l'archive a été extraite
.\PetitsPas\PetitsPas.exe --paquet "$env:LOCALAPPDATA\petits-pas\essai-L6"
```

Si ce chemin existe déjà, choisir un autre nom. La fenêtre doit présenter
« Installer Petits Pas ». Installer une école fictive, conserver les
identifiants affichés, se connecter comme direction et constater que
« Sauvegardes locales » est accessible via « Gérer l'école ».

## 2. Créer et retrouver des données

Créer une classe fictive, l'activer et l'attribuer à un enseignant fictif.
Ajouter un élève fictif, puis une observation avec une image de test. Vérifier
que l'image s'affiche, que la compétence et l'observation sont visibles et
qu'un carnet PDF peut être généré et ouvert. Fermer **la fenêtre entière**, puis
relancer exactement la même commande avec le même `--paquet` : école, classe,
élève, observation et image doivent être présents. Une seconde installation ne
doit pas être proposée.

## 3. Sauvegarder et restaurer depuis l'interface

Comme direction, aller dans « Gérer l'école → Sauvegardes locales » et cliquer
« Télécharger une sauvegarde ». Vérifier qu'un ZIP est réellement enregistré
hors du paquet de test ; retenir son chemin et sa date. Le ZIP doit contenir
`manifest.json`, `carnet.sqlite3`, `secret-key` et l'image sous `media/`.

Modifier ensuite l'observation (par exemple son commentaire), et relever la
nouvelle valeur. Sélectionner le ZIP dans « Restaurer une sauvegarde » :

1. Avant confirmation, vérifier la date annoncée, le chemin du paquet à
   remplacer et le dossier où l'état actuel sera conservé. Annuler une
   première fois : le commentaire modifié doit rester présent.
2. Sélectionner à nouveau le ZIP, confirmer, puis cliquer « Appliquer la
   restauration et redémarrer ». Attendre le réaffichage de la fenêtre et se
   reconnecter si nécessaire ; en navigateur externe, relancer manuellement
   l'application avec le même `--paquet`.
3. Vérifier le récapitulatif de la direction : date de la sauvegarde, nombre
   de médias et emplacement de l'ancien paquet. L'observation et l'image
   doivent retrouver leur état **avant** la modification. Le ZIP téléchargé
   doit toujours exister et le dossier de l'ancien paquet doit contenir l'état
   modifié ; ce dossier n'est pas un ZIP.

Fermer et relancer une dernière fois : l'état restauré doit persister. Ne
supprimer ni le ZIP ni l'ancien paquet tant que ces contrôles ne sont pas
terminés.

## Compte rendu

Après les vérifications directes, tester aussi l'installation facultative
#L7 sur le même OS : sous Ubuntu lancer `bash PetitsPas/installer-paquet-linux.sh`
depuis le dossier extrait et ouvrir « Petits Pas » dans le menu des
applications ; sous Windows ouvrir `PetitsPas/Installer-PetitsPas.cmd` et
utiliser le raccourci du menu Démarrer. Le raccourci ouvre le paquet par
défaut ; pour contrôler un paquet de test situé ailleurs, relancer l'exécutable
installé avec le même `--paquet`. Confirmer que l'installation n'a modifié
aucun des deux paquets.
Pour tester une mise à jour, installer une seconde archive, contrôler que le
raccourci pointe sur la nouvelle version et que le dossier de l'ancienne est
toujours présent.

| Contrôle | Résultat / remarque |
| --- | --- |
| OS, version, exécution Actions | |
| Première installation et connexion | |
| Persistance après fermeture | |
| Image et PDF | |
| Téléchargement et contenu du ZIP | |
| Annulation sans changement | |
| Restauration et redémarrage | |
| Ancien paquet et ZIP conservés | |
| Persistance après second lancement | |
| Installation, raccourci et mise à jour (#L7) | |

En cas d'échec, noter l'étape, le message et le moteur graphique ; ne jamais
envoyer une base ou un ZIP contenant des données réelles dans un ticket public.
