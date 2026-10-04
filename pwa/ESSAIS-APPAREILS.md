# Retours sur postes et tablettes (#PWA9)

Cette feuille aide à recueillir les retours. Elle n'est pas un jalon bloquant
pour poursuivre le prototype, publier ses évolutions ou démarrer des essais.
Les tests automatiques restent exécutés en CI. Utiliser des données fictives.

Noter appareil, système, navigateur/version, adresse PWA, version affichée,
volume de données et résultat (réussi, difficile ou impossible).

1. Ouvrir en ligne, attendre l'école ; installer depuis le bouton ou le menu
   si proposé. Fermer puis ouvrir depuis l'icône ou la même adresse.
2. Créer une classe et un enfant fictifs, saisir une réussite et une réalisation
   avec image ; vérifier le texte et la photo après fermeture puis réouverture.
3. Couper le réseau après le premier chargement ; rouvrir, se reconnecter,
   consulter et saisir. Réactiver le réseau. Le libellé du réseau est indicatif,
   pas une preuve d'accès à Internet ou de synchronisation.
4. Avec la direction, exporter un ZIP, vérifier sa présence dans les fichiers,
   puis le restaurer sur une autre installation PWA ou autonome compatible.
   Vérifier l'image et les comptes. Continuer sur une seule copie.
5. Imprimer un carnet et une grille, puis plusieurs carnets ; vérifier la
   fenêtre d'impression, les images et les pages produites.
6. Publier une évolution et utiliser les deux boutons de mise à jour ; vérifier
   la nouvelle version et les données. Essayer l'état de récupération.

Les essais Linux/Chromium automatisés ne prouvent pas une installation réelle
sur Windows, Android ou iPad. Relever les difficultés au fil de l'usage, sans
annoncer ces plateformes comme toutes validées. Ne pas provoquer de coupure
de courant avec des données à conserver.

## Pourquoi 64 Mio ?

C'est un plafond applicatif du prototype, pas la taille maximale de SQLite,
OPFS ou du disque. Pyodide charge encore base et médias dans MEMFS ; sauvegarde,
restauration, ZIP et transport HTTP créent des buffers temporaires. Les 550
photos fictives déjà qualifiées approchent ce plafond ; le tas WASM ne mesure
pas toute la mémoire du navigateur. Un simple changement de constante n'est
pas une solution pour une grosse école.

Si les usages demandent davantage, mesurer avec le banc disponible puis réduire
les copies et, si nécessaire, sortir les médias de MEMFS ou changer le stockage
SQLite. Garder export, import et reprise cohérents. Ce travail n'exige pas une
campagne préalable en école ; les retours sur appareils guideront l'ajustement.
