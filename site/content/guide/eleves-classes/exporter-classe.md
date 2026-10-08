+++
title = "Exporter une copie de sa classe"
description = "Extraire une classe pour l’utiliser dans une nouvelle installation locale."
fiche = true
categorie = "eleves-classes"
publics = ["responsable"]
intentions = ["exporter", "classe", "transfert", "ZIP", "copie"]
prerequis = "Une version proposant l’export est installée ; vous êtes responsable actif de la classe ; sur un service, l’export de classe est autorisé."
depart = "Page de la classe → Transférer cette classe → Exporter cette classe"
statut = "disponible"
+++

## Créer une copie indépendante

Sur la page de votre classe, dépliez **Transférer cette classe**, puis ouvrez
**Exporter cette classe**. Cette opération est également proposée dans le
programme Windows/Linux et dans l’application navigateur. Sur un service,
son autorisation est indépendante de celle d’exporter l’école entière.

La copie contient cette classe pour son année scolaire : enfants non archivés,
états lisibles pour cette année, traces et bilans non supprimés, référentiel et
adaptations applicables. Les autres classes et années restent exclues. Les
traces partagées deviennent des traces individuelles. Pour un enfant désormais
scolarisé ailleurs, les traces et bilans sont inclus seulement si vos droits
actuels permettent encore leur consultation. Un média n’est copié
que si vous pouvez déjà le télécharger. Une ancienne année peut conserver un
état inconnu : l’export ne reconstitue pas le passé.

1. Confirmez votre mot de passe actuel.
2. Choisissez et répétez un nouveau mot de passe pour la copie locale.
3. Lisez la confirmation et cliquez sur **Créer la copie de cette classe**.

Sur un service, la préparation continue en arrière-plan. Revenez sur la page,
puis téléchargez le ZIP lorsqu’il est prêt. Il reste disponible pendant
24 heures. Sur votre appareil, le téléchargement suit directement la
préparation : gardez l’application ouverte.

Le ZIP contient des données privées. Conservez-le sur un appareil protégé,
et gardez le nouveau mot de passe séparément.

## Utiliser la copie

Dans une nouvelle installation locale de version compatible, ouvrez
**Vérifier un ZIP sans remplacer mon école**, puis **Utiliser ce ZIP comme école
sur cet appareil**. Vous pouvez d’abord [vérifier le ZIP dans une copie indépendante]({{< relref "/guide/local/verifier-zip/" >}}).
La PWA conserve ses limites de volume ; utilisez le programme Windows/Linux si
la copie les dépasse.

Connectez-vous avec votre identifiant et le nouveau mot de passe. Vous êtes
responsable de la classe et disposez de la direction de la petite école locale,
qui ne contient que cette classe. Cela ne change aucun droit sur l’installation
source. Les autres personnes référencées n’ont pas accès à la copie.

Les deux copies évolueront indépendamment, sans synchronisation. Ce ZIP ne
permet pas de fusionner la classe dans une école existante. Pour un transfert
vers une nouvelle école du service, contacter l'exploitant : voir le
[parcours d'import]({{< relref "/guide/service/importer-zip/" >}}).
Pour un transfert définitif, convenez avec l’équipe du moment où les saisies cessent dans l’ancien
emplacement.

Cette extraction ne remplace pas la sauvegarde complète de l’installation
locale et ne renouvelle pas son rappel de sauvegarde.
