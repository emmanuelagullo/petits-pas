+++
title = "Exporter l’école vers un appareil"
description = "Préparer une copie complète de l’école au format ZIP commun aux modes locaux."
fiche = true
categorie = "local"
publics = ["direction"]
intentions = ["exporter", "ZIP", "transfert", "école", "local"]
prerequis = "Une version proposant l’export est installée ; le service l’a autorisé pour votre école ; vous exercez une direction active."
depart = "Gérer l’école → Exporter l’école"
statut = "disponible"
+++

## Préparer la copie

Dans **Gérer l’école**, ouvrez **Exporter l’école**. Si ce bouton n’apparaît
pas, demandez à la personne chargée du service si l’export est autorisé et
configuré. Les anciennes versions ne proposent pas cette fonction.

Le ZIP comprend toutes les classes et années conservées, les élèves,
observations, bilans, médias et référentiels, avec leurs adaptations.
Il comprend aussi les contenus internes et les données conservées après une
suppression logique. Toute personne possédant le ZIP peut en extraire les
données : protégez le fichier comme les données de l’école.

1. Confirmez avec votre mot de passe sur le service.
2. Choisissez et répétez un **nouveau mot de passe pour la copie locale**,
   différent de celui du service. Conservez-le séparément du ZIP.
3. Cochez la confirmation, puis cliquez sur **Préparer le ZIP**.

La préparation continue si vous fermez la page. Revenez plus tard et utilisez
**Actualiser**. Un seul export peut être en préparation ou disponible pour
l’école. Les sessions, mots de passe du service et secrets du second facteur
ne sont pas transportés ; les invitations ne restent pas utilisables.

## Télécharger le ZIP

Quand le fichier est prêt, la page indique la date de l’état copié, la taille
du téléchargement et son expiration, 24 heures après sa préparation. Confirmez
avec votre mot de passe du service, puis cliquez sur **Télécharger le ZIP**.

Le serveur permet de reprendre un téléchargement interrompu tant que le même
ZIP reste disponible et que votre accès est toujours autorisé. La reprise
effective dépend du navigateur ou du logiciel de téléchargement. Quelques Go
peuvent demander plusieurs dizaines de minutes sur une connexion lente.

Vérifiez que le téléchargement est terminé. Le fichier temporaire sur le
service est effacé automatiquement après expiration ; le ZIP téléchargé reste
sous votre responsabilité. Cet export est distinct des sauvegardes automatiques
du service.

## Ouvrir la copie

La page indique si le volume respecte les limites actuelles du navigateur :
256 Mio décompressés, 5 000 entrées et 64 Mio par fichier ou pour la base.
Les transferts progressifs évitent de charger tous les médias en mémoire ;
ces limites demeurent les volumes qualifiés. Un ZIP plus volumineux peut être
ouvert avec le programme Windows/Linux, avec assez d’espace disque.

Utilisez une version locale identique ou compatible plus récente. Commencez
par [vérifier le ZIP dans une copie indépendante]({{< relref "/guide/local/verifier-zip/" >}}).
Connectez-vous avec l’identifiant indiqué sur la page d’export et le nouveau
mot de passe choisi. Les autres personnes restent identifiées dans l’historique,
mais leur accès local est désactivé. Les droits de classe restent distincts de
la direction ; l’export n’attribue pas automatiquement une fonction pédagogique.

Sur un appareil vide, le parcours permet d’installer explicitement le ZIP.
Sur un appareil déjà utilisé, suivez la
[restauration locale]({{< relref "/guide/local/restaurer-paquet/" >}}), qui remplace
l’école locale après confirmation.

La copie et le service évoluent indépendamment. Pour changer définitivement de
mode, convenez avec l’équipe du moment où les saisies cessent dans l’ancien
emplacement. L’import, le remplacement ou la fusion dans le service partagé
ne sont pas proposés par cette fonction.
