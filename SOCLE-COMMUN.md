# Pas communs — état courant et historique des extractions

La version `pas-communs` 0.8.0 est publiée et adoptée au 20 octobre 2026.
Préserver ses octets et son tag ; une correction documentaire ne la republie pas. L'URL et l'empreinte réellement adoptées sont celles
de requirements-communs.txt. Les sections #SOC ci-dessous sont historiques.
Lire aussi QUALIFICATION.md dans le dépôt du socle.
La façade `suivi.paquet_local` conserve l'API, les confirmations en mémoire,
le rappel d'export local et les métadonnées de projection. Droits, exports,
imports et sélection des secrets restent dans Petits Pas. Aucun modèle Django,
format historique ou nom de stockage navigateur n'est déplacé.

## Installer

Le wheel public est fixé par URL et SHA-256 dans `requirements-communs.txt`,
inclus par les profils serveur, bureau et navigateur. Installer les dépendances
habituelles suffit. Pas de service additionnel, de Git ni de PyPI à configurer.
La publication immuable du wheel candidat doit précéder le push des
consommateurs qui le requièrent. Un téléchargement manquant ou altéré est refusé.

Avant cette publication, les essais peuvent employer le wheel local candidat :
installer les autres dépendances avec un fichier temporaire privé d'inclusion du
socle, puis `pip install /chemin/pas_communs-0.8.0-py3-none-any.whl`.
Ne pas committer de chemin local ni de dépendance à une branche mobile.
En développement conjoint : `pip install -e ../pas-communs` après préparation du
backend de construction. Les releases utilisent toujours le wheel fixé.

## Programme et PWA

PyInstaller collecte le module `pas_communs` installé par le profil bureau.
Le constructeur PWA inclut le même wheel pur dans ses ressources, contrôlé
par l'empreinte épinglée. `--wheels` doit aussi contenir ce wheel exact ; ce
cache peut être utilisé avant publication ou hors réseau. Une version différente
ou absente est refusée. Ne pas distribuer une copie du moteur dans application.zip.

Les anciens ZIP Petits Pas sans champ `application` sont acceptés uniquement avec
leur format historique. Les nouveaux ajoutent `application: petits-pas` sans
changer version, noms de fichiers ni métadonnées d'export. Les anciens validateurs
restent capables de les lire. Aucun relèvement des plafonds PWA n'est effectué.
Les manifestes OPFS historiques sans identité explicite restent lisibles ; aucun
changement de leurs noms ni de leurs espaces n'est nécessaire.

## Vérifier

Conserver les tests `test_paquet_local`, `test_transferts_pwa`, les tests Django
exports/imports, sauvegardes et aperçus, les essais PWA et les constructions
Windows/Linux. La CI du socle ne remplace pas la qualification du produit.
La CI `0.10` et sa publication doivent rester sur le commit préparé avant #SOC2.


## Runtime local et construction (#SOC3)

La version 0.2.0 a ajouté `pas_communs.local` et `pas_communs.construction`.
Le lanceur Petits Pas conserve ses options, ses chemins et ses parcours métier.
Ses fonctions publiques restent des façades ; les mécanismes communs sont
utilisés aussi par Pas à Pas — Accompagnement. Les callbacks de changement
d'espace et de restauration restent dans Petits Pas et n'accordent aucun droit.

Le `.spec` garde les ressources Petits Pas et la variable PETITS_PAS_PANGO_BIN ;
l'assemblage des plateformes est désormais commun. Les scripts de construction,
installateurs Inno Setup et archives et gestion de versions ne sont pas renommés.
La PWA embarque le nouveau wheel, mais n'importe pas les modules bureau.
Qualifier les deux programmes avant une publication ; conserver 0.10 inchangée.

## Authentification : première extraction (#SOC4a)

Le wheel 0.3.0 fournit les primitives TOTP, mots de passe et sessions. Les
façades comptes.totp, comptes.validators et comptes.backends restent en place.
Aucun modèle, migration, rôle ou parcours scolaire n’est déplacé. Les clés,
politiques d’obligation, tentatives, transactions et secours restent propres
à Petits Pas ; les profils autonomes ne changent pas de politique 2FA.

L’attente avant second facteur est désormais liée au mot de passe et au backend.
Une attente en cours avant mise à jour est abandonnée : ressaisir le mot de passe.
Les sessions déjà authentifiées restent valides. Les noms historiques de cookies
et le backend standard mémorisé par Django restent inchangés.
Le parcours CHRS renforcé reste à intégrer sous #SOC4b.

## Première extraction navigateur (#SOC5a)

Le wheel 0.4.0 embarque les modules JavaScript copiés dans `socle/` au build :
stockage OPFS/IndexedDB, transport et vérification des capacités. Les façades
historiques `pwa/storage.js`, `transport.js` et `capabilities.js` gardent leur API.
Les primitives WSGI, crypto WASM et téléchargement viennent aussi du socle.
Les noms de stockage, espaces essai/aperçu, formats anciens et limites restent
inchangés. Les nouveaux manifestes internes indiquent le produit ; les anciens
manifestes Petits Pas restent lisibles. Les ZIP publics ne changent pas.

Coque, Service Worker, Worker, transferts, inventaire, restaurations et métier
restent ici. Aucun flux scolaire ne migre dans le prototype CHRS. Construire
avec le wheel épinglé ; ne pas aller chercher des sources JavaScript sur main.
Une modification de ressource commune exige nouvelle version et nouvelle
qualification PWA du produit, comme une modification Python du socle.
Cette livraison ne publie aucun bundle ni release Petits Pas.

## Finalisation du candidat navigateur (#SOC5b)

Le wheel 0.4.0 de #SOC5a n'avait pas été publié. #SOC5b adopte ses octets finaux
et sa nouvelle empreinte, avec informations de secours et réécriture explicite
pour la restauration CHRS. Les appels et comportements par défaut Petits Pas
restent inchangés. Aucun nouveau modèle, migration ou parcours scolaire.
Publier uniquement le candidat final avant de pousser les consommateurs.
Les coques/Workers/transferts restent propres aux produits ; #SOC5 est clos
sur les bancs Chromium/Linux, sans nouvelle qualification d'appareils terrain.

## Profil serveur volontaire (#SOC6a)

Le wheel 0.5.0 ajoute le contrat HTTPS de carnet.settings_serveur. Lire
SERVEUR-SOCLE.md avant adoption. Les réglages historiques, bureau/PWA, bases,
migrations et politiques métier restent inchangés. Aucun basculement de service
n'est effectué par installation du patch. Les recettes restent #SOC6b.

## Recettes CI et candidats (#SOC6b)

La version finale 0.5.0 ajoute la recette Django et les primitives d'identité,
empreinte et validation des artefacts/bundles. Les façades scripts/publication.py
et preparer-publication-pwa.py gardent leur API et le format historique schema 1.
Les notes, choix de job, contrôles de tag/origine/cible et promotion restent
Petits Pas. Aucun publisher commun avec un jeton partagé n'est introduit.
La CI conserve PostgreSQL et les validations scolaires ; le banc serveur
ajoute Gunicorn loopback, sans connexion à une adresse publique.

## Génération PDF native (#SOC7b)

Pas communs 0.6.0 fournit les appels WeasyPrint et le récupérateur de médias.
Les façades _generer_pdf/_recuperateur_pdf/_url_media_pdf conservent leurs
signatures, les templates et les règles historiques de ressources et de droits.
Le serveur et le programme gardent WeasyPrint/Pango ; la PWA conserve son
adaptation d'impression existante. Les options de qualité scolaire ne deviennent
pas des politiques CHRS. Les PDF texte du CHRS navigateur ne remplacent pas
les carnets avec images. Publier d'abord le wheel 0.6.0 puis adopter son hash.

## #SOC3b — installateur Windows (0.7.0)

Le modèle Inno Setup et le banc PowerShell viennent du wheel ; seule
scripts/installateur-windows.json décrit le produit. AppId, dossier installé,
raccourci et données Petits Pas sont conservés. La CI compile, installe,
contrôle le programme, réinstalle et désinstalle avec un témoin de données
conservé. Les manifestes et la promotion du setup restent propres au produit.
Publier le wheel 0.7.0 avant d’adopter cette dépendance.

## Candidat 0.9.0 — copies communes

L'état préparation/confirmation historique est extrait dans RestaurationLocale.
La façade et les droits Petits Pas restent inchangés. Seules les sessions de
la préparation sont retirées pour imposer une nouvelle connexion ; la source,
les comptes, mots de passe, permissions, facteurs et clés restent intacts.
Le même mécanisme de neutralisation est utilisé pour les aperçus. Ne pousser
cette adoption qu'après publication du wheel 0.9.0 et contrôle de son empreinte.

Après construction PWA : `PWA_BUNDLE=dist/pwa-candidat node scripts/verifier-paquet-pyodide.mjs`
vérifie dans le vrai runtime la reprise du témoin 0.10, les migrations, les
sessions et la réinitialisation des façades après activation. Ce banc Node
ne remplace pas OPFS/Chromium et les essais sur appareils.
