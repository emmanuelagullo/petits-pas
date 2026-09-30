# Petits Pas

## Versions

Un tag numérique (par exemple `0.8`) identifie la même version du code sur
serveur et dans les paquets autonomes. Entre deux tags, l'application affiche
`dev.<commit>` ; ce suffixe identifie le code, sans présumer du numéro de la
prochaine release. La version est intégrée aux archives au moment de leur
construction. Pousser un tag après un commit nécessite donc une nouvelle
construction des paquets de release.

Sur Render, `RENDER_GIT_COMMIT` identifie le code effectivement déployé. Au
démarrage, l'application recherche dans la forge un tag numérique qui pointe exactement sur
ce commit dans le dépôt public (`PETITS_PAS_DEPOT_VERSIONS` permet de choisir
le miroir GitLab). Sans tag accessible, elle affiche `dev.<commit>`. Après la
création d'un tag sur un commit déjà déployé, un redémarrage du service suffit
à actualiser la version affichée ; le contenu du code ne change pas. Un
hébergement sans Render peut définir `CARNET_VERSION` lorsqu'il
contrôle explicitement la version promue.

Petits Pas est une application libre de suivi des apprentissages en école
maternelle. Elle vise à offrir aux équipes pédagogiques un outil simple pour
documenter les observations, préparer les bilans et produire les carnets
individuels remis aux familles.

Le projet est en cours de développement. Les environnements de démonstration
et les supports publics utilisent exclusivement des données fictives.

## Développement local

Les procédures locales et les profils de déploiement sont décrits dans
`DEPLOIEMENT.org`, `ATELIER-PEDAGOGIQUE.org` et `REPRODUCTIBILITE.org`.

### Application locale (#L1–L2)

Avec les dépendances Python du projet installées, dans le shell Guix habituel,
ajouter `python-pygobject` et `webkitgtk-for-gtk3` au `use guix` de `.envrc`.
PyWebView sous Linux requiert PyGObject et l'API `WebKit2` 4.1 de WebKitGTK.
Le paquet `webkitgtk` seul n'expose pas cette API. Recharger `direnv`, puis
créer un environnement Python qui voit les paquets Guix :

```sh
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-local.txt
python -c "import gi; gi.require_version('WebKit2', '4.1'); from gi.repository import WebKit2"
python scripts/lancer-local.py
# Ou, pour un autre emplacement :
python scripts/lancer-local.py --paquet /chemin/vers/mon-paquet
```

Sur un paquet neuf, la fenêtre ouvre **Installer Petits Pas** : elle crée
l'école, un premier compte personnel de direction et la trame pédagogique
provisoire. La même fenêtre propose ensuite la connexion ordinaire. Sur un
paquet déjà initialisé, elle ouvre directement la connexion et ne modifie ni
les comptes ni le référentiel. Le formulaire est inaccessible dans les
déploiements serveur ou dès qu'une école ou un compte existe dans la base.

La commande facultative `--creer-ecole "Mon école" --commune "Ma commune"`
utilise la création d'école existante, charge
`referentiel/trame-cycle1.yaml` (une trame pédagogique provisoire) et affiche
les identifiants initiaux dans le terminal. Elle refuse d'ajouter une seconde
école dans ce paquet. Pour un autre chemin, lui passer aussi `--paquet`.
Ne lancer l'initialisation qu'une fois et conserver les mots de passe affichés.
Si une école a été créée avec la première version de #L1, charger la trame
explicitement, sans recréer l'école :

```sh
python scripts/lancer-local.py --charger-referentiel
```

Cette commande concerne les anciens paquets qui n'utilisent pas encore les
référentiels annuels. Les nouvelles installations préparent automatiquement
leur trame de travail annuelle ; les paquets repris avec #R3 refusent le
rechargement direct, afin de conserver le sens des observations. Le choix et
la mise à jour des bases seront proposés dans le chantier des référentiels.
La reprise des bases existantes est décrite dans `DIAGNOSTIC-REFERENTIELS.org`.

Le lanceur ouvre PyWebView sur Django, lié uniquement à `127.0.0.1` sur un
port libre. Fermer la fenêtre arrête le serveur. Par défaut, les nouveaux
paquets résident sous `~/.local/share/petits-pas/paquet-autonome/` (ou sous
`$XDG_DATA_HOME/petits-pas/paquet-autonome/` si cette variable est définie),
hors du dépôt : une nouvelle extraction ou mise à jour du code conserve ainsi
les données. Le chemin se règle par `PETITS_PAS_PAQUET_AUTONOME` ou `--paquet`
(prioritaire). Un chemin relatif est interprété depuis le répertoire de
lancement. Le paquet contient `carnet.sqlite3`, `media/`, `secret-key`, les
éventuelles `sauvegardes-migrations/`, et `staticfiles/` (recréé depuis le
code). Le courrier est désactivé.

**Paquet créé avec #L1 dans le dépôt :** fermer la fenêtre, puis le copier
explicitement vers le nouvel emplacement par défaut :

```sh
python scripts/lancer-local.py --paquet ./paquet-autonome \
  --copier-paquet "${XDG_DATA_HOME:-$HOME/.local/share}/petits-pas/paquet-autonome"
python scripts/lancer-local.py
```

La copie vérifie la base SQLite et conserve le paquet d'origine. L'ancienne
option `--deplacer-paquet` reste acceptée pour les commandes déjà utilisées.
La copie ne remplace jamais une destination existante. Le lanceur refuse de créer un paquet
vide à l'emplacement par défaut s'il détecte encore l'ancien paquet dans le
dépôt : il affiche la commande de transfert. Après vérification du nouveau
paquet, l'ancien peut être archivé ou supprimé manuellement pour éviter de
modifier par mégarde deux jeux de données divergents. Pour rester sur l'ancien
emplacement sans transfert, lancer explicitement
`python scripts/lancer-local.py --paquet ./paquet-autonome`.

Les migrations s'appliquent au démarrage. Lorsqu'une mise à jour du code exige
une migration, une copie de la base SQLite est créée d'abord dans
`sauvegardes-migrations/`. Le lanceur refuse aussi l'ouverture simultanée du
même paquet dans deux instances. Ces copies techniques ne remplacent pas une
sauvegarde complète de la base **et** des médias, prévue pour #L4.

Après la première connexion, créer une classe, ajouter une trace avec photo,
générer son carnet PDF et fermer la fenêtre. Relancer ensuite la même commande
et vérifier que l'école, la trace et le PDF sont toujours disponibles. Si le
moteur Web n'offre pas le téléchargement attendu, relever précisément le
comportement avant de considérer cette vérification acquise.

Ce jalon est un prototype à lancer depuis les sources, sans installateur :
le téléchargement des PDF dépend du moteur Web installé. Conserver ensemble
la base, les médias et la clé du paquet pour préparer une sauvegarde ou un
transfert ; `staticfiles/` peut être reconstruit au lancement depuis le code.
Une copie faite pendant que l'application tourne peut être incohérente.
Un installateur système complet reste un jalon ultérieur.

### Dossiers autonomes Linux et Windows (prototype)

Les constructions PyInstaller sont propres à chaque système : construire
**sous Linux** pour Linux, **sous Windows** pour Windows. Elles embarquent
Django, les modèles, les gabarits, les statiques et la trame pédagogique ;
les données de l'école restent **hors** de l'exécutable. Il ne s'agit pas
d'une distribution universelle testée.

Après extraction, l'installation facultative par utilisateur (#L7) copie
le programme dans un dossier portant l'empreinte de l'exécutable et crée un
lanceur. Elle ne nécessite pas de droits administrateur :

```sh
# Ubuntu : dans le dossier PetitsPas extrait
bash installer-paquet-linux.sh
```

L'artefact CI `PetitsPas-windows` contient une archive ZIP destinée aux essais
techniques et au lancement sans assistant graphique. Sous Windows, ouvrir
`PetitsPas/Installer-PetitsPas.cmd` dans l'Explorateur :
un raccourci « Petits Pas » est créé dans le menu Démarrer. Le programme peut
également être lancé directement depuis le dossier extrait. L’installateur
affiche la progression de la vérification et de la copie
des fichiers. Le raccourci démarre directement le programme graphique ; le
journal est conservé sous `%LOCALAPPDATA%\petits-pas\logs\dernier-demarrage.log`.
En cas d'échec au démarrage, une boîte de dialogue indique le chemin du journal.
Le lanceur `.cmd` reste disponible pour les essais techniques de l'archive.

L'artefact CI `PetitsPas-Setup-windows` contient l'**installateur graphique
recommandé pour les essais sur Windows** : extraire le ZIP enveloppe de GitHub
Actions, puis ouvrir `PetitsPas-Setup-<version>-x64.exe`. Il installe le même dossier PyInstaller pour
l'utilisateur courant, sans élévation, et ajoute une entrée de désinstallation
Windows. S'il détecte une installation précédente réalisée avec le même setup,
il annonce la version installée et demande confirmation avant de la remplacer.
La désinstallation laisse le paquet de données de l'école intact.
Le menu Démarrer ouvre directement l'exécutable sans console. Le paquet Windows
embarque désormais les DLL Pango issues de MSYS2 UCRT64 et contrôle en CI la
création d'un PDF minimal par l'exécutable construit. Ce contrôle ne remplace
pas l'essai du carnet PDF sur le poste cible. Ne pas substituer cet artefact à
l'archive publiée avant les essais réels décrits dans
`VALIDATION-PAQUET-AUTONOME.md`.

Pour construire l'installateur après le paquet PyInstaller, installer Inno
Setup, puis exécuter :

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" "/DAppVersion=0.7-dev" "/DOutputDir=$((Resolve-Path dist).Path)" scripts\PetitsPas-Windows.iss
```

Pour diagnostiquer une version
antérieure à ce lanceur, ouvrir PowerShell et exécuter :

```powershell
$version = (Get-Content "$env:LOCALAPPDATA\Programs\PetitsPas\actuelle" -Raw).Trim()
& "$env:LOCALAPPDATA\Programs\PetitsPas\$version\PetitsPas.exe"
```

Pour mettre à jour, extraire la nouvelle archive et relancer son installateur : l'ancienne
version reste dans son dossier pour permettre un retour manuel. Les données
restent dans `paquet-autonome`, à l'emplacement déjà configuré ; installer ou
mettre à jour le programme ne copie ni ne restaure les données. Quitter
l'application avant de démarrer la version nouvellement installée. Le lanceur
Ubuntu reste destiné à un environnement disposant de GTK, WebKit2 et Pango ;
la construction Ubuntu n'est pas une distribution Guix.
Pour gérer les versions déjà installées (#L8), exécuter depuis le dossier
extrait (fermer l'application avant un retour ou un nettoyage) :

```sh
bash gerer-versions-linux.sh --lister
bash gerer-versions-linux.sh --revenir
bash gerer-versions-linux.sh --nettoyer
```

Sous Windows, lancer depuis l'archive extraite :

```powershell
.\Installer-PetitsPas.cmd -Action Lister
.\Installer-PetitsPas.cmd -Action Revenir
.\Installer-PetitsPas.cmd -Action Nettoyer
```

Une version est identifiée par l'empreinte du programme **et de ses ressources**.
Le retour change seulement le raccourci et peut être inversé par un second
retour. Le nettoyage ne retire que les versions plus anciennes que l'active
et la précédente ; il ne touche ni aux ZIP de sauvegarde ni au paquet de
données. Une ancienne archive peut être réinstallée si nécessaire.

Sous Linux, dans le shell Guix déjà utilisé pour ouvrir la fenêtre locale
(avec PyGObject et WebKit2 disponibles) :

```sh
bash scripts/construire-paquet-linux.sh
./dist/PetitsPas/PetitsPas
```

La construction Linux utilise un venv temporaire, supprimé à la fin ; elle
ne modifie pas `.venv` ou un ancien `.venv-paquet` du dépôt.
Sur Guix, si le bootloader PyInstaller référence un chargeur ELF absent ou
ne trouve pas `libz.so.1`, le script adapte le binaire avant de vérifier le
paquet. Pour corriger un binaire déjà construit sans relancer PyInstaller :
`bash scripts/corriger-interpreteur-linux.sh dist/PetitsPas/PetitsPas`, puis
`./dist/PetitsPas/PetitsPas --verifier-distribution`. Le script ne modifie le
binaire que si son chargeur ou zlib manque et nécessite `patchelf` ou
`guix shell`.
Le script crée `dist/PetitsPas-linux.tar.gz`. Sur la machine de destination,
GTK, WebKit2 et les bibliothèques natives de WeasyPrint doivent rester
disponibles ; le programme n'est pas un AppImage portable entre toutes les
distributions. Si l'environnement Guix ne permet pas de construire ou d'ouvrir
l'exécutable, le lancement Python local existant reste utilisable.

Sous Windows, depuis **PowerShell dans le dépôt**, avec Python 3 (64 bits)
et MSYS2 UCRT64 installés sur la machine de construction, installer Pango
depuis le shell UCRT64 (`pacman -S mingw-w64-ucrt-x86_64-pango`), puis :

```powershell
$env:PETITS_PAS_PANGO_BIN = 'C:\msys64\ucrt64\bin'
powershell -ExecutionPolicy Bypass -File scripts/construire-paquet-windows.ps1
.\dist\PetitsPas\PetitsPas.exe
```

Le script produit `dist/PetitsPas-windows.zip` : décompresser **tout** le
dossier `PetitsPas` sur le poste de destination, puis ouvrir `PetitsPas.exe`.
Si le miroir GitHub contient ce changement et que ses Actions sont activées,
l'action **Paquets autonomes Linux et Windows (prototype)** construit les deux
dossiers à chaque modification du code sur `main`. Elle peut aussi être
lancée depuis l'onglet **Actions → Run workflow**. Chaque exécution fournit
les artefacts `PetitsPas-Setup-windows`, `PetitsPas-windows` et
`PetitsPas-linux`. Pour essayer l'installation graphique Windows, télécharger
`PetitsPas-Setup-windows` et extraire son ZIP enveloppe. L'artefact
`PetitsPas-windows` fournit le dossier portable et l'ancien installateur
en ligne de commande, après extraction de ses deux niveaux de ZIP.
Télécharger l'artefact Linux puis extraire
`PetitsPas-linux.tar.gz` ; ce binaire est construit sur Ubuntu 24.04 et
nécessite les bibliothèques GTK/WebKit/Pango de la machine cible. Les Actions
doivent être activées sur le miroir et le workflow présent sur sa branche
par défaut pour que le lancement manuel soit disponible.
Pour partager une construction avant validation, transmettre les artefacts
Actions de la même exécution : aucun tag n'est créé. Après les essais Linux
et Windows et une CI verte sur le commit à publier, créer **un seul tag Git local**
sur ce commit, puis le pousser vers les deux dépôts (remplacer le SHA d'exemple) :

```sh
git tag -a 0.7 SHA_DU_COMMIT_VALIDE -m 'Petits Pas 0.7'
git push inria 0.7
git push github 0.7
```

Le push du tag GitHub lance une nouvelle exécution du workflow des paquets :
attendre qu'elle soit verte et utiliser **son numéro** pour publier le setup
Windows `PetitsPas-Setup-0.7-x64.exe` et les archives. Le script refuse un
setup `0.7-dev.*` provenant du push sur `main` :

```sh
bash scripts/publier-paquets.sh NUMERO_EXECUTION TAG
```

Le script détecte `gh` et `glab`. Avec `gh` seul, il récupère les archives
GitHub Actions, vérifie le commit de l’exécution et les tags sur les deux
forges, puis publie une préversion GitHub contenant le setup Windows recommandé,
l'archive Linux et l'archive technique Windows. Il indique
ensuite comment créer la release GitLab depuis son interface, avec trois liens
vers les mêmes fichiers GitHub. Avec les deux CLI, il publie aussi les fichiers
dans le registre de paquets GitLab et crée les deux releases.

Sans `gh`, mais avec `glab`, télécharger manuellement les trois fichiers de la
même exécution GitHub Actions (après extraction de leurs ZIP enveloppes),
vérifier son SHA dans GitHub Actions puis lancer :

```sh
bash scripts/publier-paquets.sh NUMERO_EXECUTION TAG \
  /chemin/PetitsPas-linux.tar.gz /chemin/PetitsPas-Setup-0.7-x64.exe \
  /chemin/PetitsPas-windows.zip SHA_DU_COMMIT
```

Le script vérifie que le SHA fourni correspond aux tags, mais ne peut pas
contrôler automatiquement l’exécution GitHub sans `gh`. Sans aucun des deux
CLI, il ne publie rien et donne les étapes pour les deux interfaces web.
L’authentification et les droits de publication restent nécessaires sur les
forges utilisées (`gh auth login`, éventuellement
`glab auth login --hostname gitlab.inria.fr`).
Si une étape distante échoue, vérifier les releases déjà créées avant toute
nouvelle tentative : le script ne remplace pas une release existante.
Une release GitHub, même marquée « pre-release », requiert un tag ; les
artefacts Actions permettent de tester sans tag.

Pour les utilisateurs, le point d’entrée du site public est la
[fiche de téléchargement](https://petits-pas.gitlabpages.inria.fr/petits-pas/guide/local/telecharger-programme/) :
elle renvoie vers les versions GitHub publiées et distingue l'installateur
graphique Windows des archives et des artefacts temporaires d’Actions.
La release 0.6 antérieure à ce changement ne contient que l'archive Windows.
Les erreurs de démarrage sont consignées dans le journal local. Le poste
doit disposer du moteur Microsoft WebView2. Le programme lui-même n'a pas
besoin d'une installation Python ou MSYS2 sur ce poste.

Linux : données dans `${XDG_DATA_HOME:-~/.local/share}/petits-pas/paquet-autonome`.
Windows : données dans `%LOCALAPPDATA%\petits-pas\paquet-autonome`.
`--paquet CHEMIN` et `PETITS_PAS_PAQUET_AUTONOME` restent utilisables dans les
deux constructions ; les ZIP de sauvegarde permettent de transférer une école
entre les deux systèmes. Éviter d'ouvrir simultanément le même paquet sur un
répertoire partagé. Pour diagnostiquer un dossier construit sans créer d'école :
`PetitsPas.exe --verifier-distribution` (Windows) ou
`./PetitsPas --verifier-distribution` (Linux).

### Sauvegarde et restauration du paquet local (#L4)

Dans la fenêtre locale, la direction ouvre **Gérer l'école → Sauvegardes
locales**. « Télécharger une sauvegarde » produit un ZIP avec la base SQLite,
les médias et la clé du paquet. PyWebView ouvre une boîte d'enregistrement
selon le moteur Web installé. Le ZIP contient des données privées :
à conserver comme le paquet lui-même.

Pour restaurer, sélectionner ce ZIP dans la même page. Le contenu et la base
SQLite sont vérifiés avant toute modification. La page indique la date de
création de la sauvegarde, le paquet à remplacer et le chemin où sera conservé
le paquet actuel. Confirmer explicitement, puis utiliser « Appliquer la
restauration et redémarrer » : le serveur s'arrête, le paquet est remplacé et
la fenêtre se rouvre. En dehors de PyWebView, fermer la fenêtre et relancer
manuellement. Un indicateur d'activité accompagne la vérification du ZIP.
Le paquet précédent est conservé par renommage dans un dossier voisin : cette
protection automatique ne produit pas de ZIP. L'écran de confirmation propose
de télécharger en plus un ZIP de l'état actuel avant de restaurer, sans
l'imposer. Un récapitulatif apparaît à la connexion de la direction.
Les archives antérieures restent utilisables, mais
leur date de création ne peut pas être affichée. Une préparation annulée ou
abandonnée à la fermeture ne modifie pas le paquet.
Une restauration en attente bloque les nouvelles écritures. Les éventuels
fichiers `staticfiles/` sont reconstruits au démarrage ; les copies techniques
`sauvegardes-migrations/` restent dans le paquet remplacé. Il n'est pas
nécessaire de restaurer un compte ou un référentiel séparément.

Le parcours de validation des exécutables Windows et Ubuntu (installation,
persistance, sauvegarde, restauration et redémarrage) est décrit dans
[`VALIDATION-PAQUET-AUTONOME.md`](VALIDATION-PAQUET-AUTONOME.md).

## Site public

Le site de présentation est construit avec Hugo depuis le répertoire `site/` :

```sh
sh scripts/preparer-site.sh
python3 scripts/verifier-guide-pratique.py
hugo --source site --minify
```

Hugo rend directement les contenus Markdown et Org-mode. Seuls les documents
explicitement placés dans `site/content/` sont publiés. Le contrôle préalable
vérifie les métadonnées des fiches pratiques, leurs liens internes et la
cohérence entre les captures utilisées et les scénarios fictifs déclarés.

## Licence

Le code de Petits Pas est distribué sous licence
[GNU Affero General Public License, version 3 ou ultérieure](LICENSE)
(`AGPL-3.0-or-later`). Cette licence autorise notamment l'usage, l'étude, la
modification, la redistribution et l'auto-hébergement du logiciel.

La politique applicable à la documentation, aux illustrations et aux données
est détaillée dans [CONTENUS-ET-LICENCES.md](CONTENUS-ET-LICENCES.md).
