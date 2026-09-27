# Audit du parcours Windows autonome (après 0.6)

## Périmètre et constat

Audit du code de `main` après le tag `0.6`, sans essai sur un poste Windows.
Le commit postérieur `f6ff3f9` ajoute une progression à la copie et garde la
console ouverte en cas d'échec au démarrage : ces améliorations ne figurent
donc pas nécessairement dans les archives de la release 0.6.

Le parcours publié demande de télécharger un ZIP, de l'extraire entièrement,
d'ouvrir `PetitsPas/Installer-PetitsPas.cmd`, puis de lancer le raccourci créé.
Ce script ouvre PowerShell, calcule les SHA-256 de tous les fichiers, copie
`_internal` et l'exécutable dans un dossier nommé par empreinte sous
`%LOCALAPPDATA%\Programs\PetitsPas`, et crée un raccourci du menu Démarrer.
Les données restent séparées sous `%LOCALAPPDATA%\petits-pas\paquet-autonome`.

| Observation vérifiable dans le dépôt | Conséquence pour l'utilisateur |
| --- | --- |
| `Installer-PetitsPas.cmd` lance un script PowerShell ; la progression est `Write-Progress`. | Une fenêtre technique apparaît ; le calcul initial peut durer sans indication compréhensible dans la release 0.6. |
| Le raccourci cible `Demarrer-PetitsPas.cmd` et le `.spec` définit `console=True`. | Une console reste visible pendant l'utilisation. Le journal du dernier lancement existe après `f6ff3f9`. |
| Le `.spec` collecte pywebview ; `--verifier-distribution` n'ouvre aucune fenêtre. | Le contrôle CI ne prouve ni le chargement du moteur Windows ni la création d'un PDF. |
| `README.md` exige WebView2 pour la fenêtre et Pango pour le PDF. | L'archive Python seule ne constitue pas encore un logiciel autonome complet pour un poste neuf. |
| Le gestionnaire conserve les dossiers de versions et expose `Lister`, `Revenir`, `Nettoyer` en ligne de commande. | Aucune entrée Windows « Applications installées / Désinstaller » ; le retour arrière n'est pas adapté aux enseignants. |
| Le premier démarrage applique automatiquement les migrations à la base, avec copie préalable de la base seulement. | Un ancien exécutable peut ne plus savoir ouvrir les données migrées ; un retour de raccourci ne vaut pas restauration. |

Le défaut `Failed To resolve Python.Runtime.Loader.Initialize ... pythonnet ... Python.Runtime.dll`
signalé sur un poste Windows doit être reproduit et corrigé **avant** de
qualifier un nouvel installateur. L'emballage du même exécutable ne le corrige
pas. Conserver le système et sa version, l'origine exacte de l'archive, le
journal de lancement, puis tester une machine Windows vierge avec et sans
WebView2 déjà présent ; vérifier les versions de pywebview/pythonnet embarquées
et le chargement effectif de la fenêtre. Ne joindre aucune donnée scolaire au
rapport d'erreur.

## Cible proposée

Distribuer un seul fichier `PetitsPas-Setup-<version>-x64.exe`, signé lorsque
possible. Un double-clic ouvre un assistant en français avec le nom et l'éditeur
du logiciel, une progression visible, puis « Ouvrir Petits Pas ». Installation
par utilisateur, sans droits administrateur, avec entrée au menu Démarrer et
dans « Applications installées ». Le premier lancement conserve l'écran Web
existant de création de l'école et du compte ; il ne se fait pas dans
l'assistant. Un lancement normal n'ouvre aucune console. En cas d'échec, une
boîte en français indique le problème, où trouver le journal, et permet de
l'ouvrir. Un raccourci « Diagnostic Petits Pas » peut exposer le mode console
pour le support.

**Outil recommandé : Inno Setup** autour du dossier `dist/PetitsPas` produit
par PyInstaller. Son assistant, sa progression, son désinstallateur et son mode
par utilisateur correspondent au parcours visé, sans réécrire l'application
Django/PyWebView. Garder un `AppId` stable, un numéro de version explicite et un
répertoire fixe par utilisateur. La piste MSI/WiX reste pertinente si une DSI
exige un déploiement géré ; ne pas en faire un préalable à l'essai enseignant.
Un simple habillage graphique du `.ps1` conserverait le double ZIP, les copies
manuelles et l'absence de désinstallation enregistrée.

Séparer impérativement programme et données : la désinstallation retire le
programme, ses raccourcis et son enregistrement Windows, mais **préserve** la
base, les médias, la clé et les sauvegardes. L'assistant affiche leur
emplacement et renvoie au parcours de sauvegarde existant. Une suppression
des données serait une action distincte, explicite, et ne fait pas partie de
l'installateur. Une mise à jour doit reconnaître une installation #L7
existante, éviter deux raccourcis « Petits Pas », et préserver son paquet de
données ; tester ce chemin avant diffusion.

## Ordre de réalisation conseillé

1. **Rendre le paquet Windows réellement lançable.** Reproduire l'erreur
   pythonnet sur Windows 10/11 x64, stabiliser les dépendances de construction,
   tester fenêtre, connexion, ZIP et génération d'un PDF sur un poste vierge.
   Choisir et valider une solution de distribution de WebView2 et des DLL Pango
   (avec leurs licences et architectures) ; ne pas télécharger silencieusement
   des dépendances pendant l'installation sans l'annoncer. Faire échouer la
   validation de release si ces fonctions essentielles échouent.
2. **Séparer lancement graphique et diagnostic.** Construire un exécutable
   PyInstaller `windowed` pour l'usage normal et un mode de diagnostic
   accessible. Initialiser le journal avant les imports sensibles, capturer
   les erreurs de démarrage et présenter une boîte de dialogue native. Vérifier
   le comportement des écritures vers `stdout`/`stderr` sans console et du
   redémarrage après restauration.
3. **Créer l'installateur.** Compiler le dossier PyInstaller avec Inno Setup
   dans la CI Windows ; définir version, `AppId`, `PrivilegesRequired=lowest`,
   emplacement utilisateur, icône, raccourcis et désinstallation. Installer
   depuis le seul `.exe` sur une machine sans Python ni PowerShell à manipuler.
   Tester mise à jour, réinstallation, désinstallation et migration de #L7.
4. **Publier après essais.** Produire un artefact temporaire dans Actions,
   faire valider le parcours complet sur deux postes Windows, puis publier le
   setup avec les archives existantes tant que leur retrait n'est pas décidé.
   Mettre à jour la fiche publique : téléchargement → double-clic → installation
   → ouverture. Envisager la signature du code pour une diffusion large ; la
   signature et la réputation SmartScreen sont deux sujets distincts.

## Critères de validation avant une release destinée aux enseignants

- Depuis le fichier de release : un seul téléchargement et un double-clic,
  progression explicite, pas de terminal, pas de droit administrateur demandé.
- Sur un profil Windows neuf : démarrage, création d'une école fictive,
  connexion, observation avec image, téléchargement et ouverture du PDF et du
  ZIP de sauvegarde, fermeture puis réouverture avec données intactes.
- Sur une installation #L7 existante : mise à jour sans perte des données,
  raccourci unique, diagnostic exploitable si WebView2/Pango manque.
- Désinstallation via Windows : disparition du programme et des raccourcis,
  données et sauvegardes encore présentes ; réinstallation retrouve l'école.
- En cas de migration de schéma : vérifier un scénario de récupération de la
  **base et des médias** avant de promettre « Revenir à la version précédente ».

Références de mise en œuvre :
[Inno Setup, identité et désinstallation](https://jrsoftware.org/ishelp/topic_setup_appid.htm),
[installation sans élévation](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm),
[PyInstaller et mode sans console](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html),
[dépendances Windows de WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
