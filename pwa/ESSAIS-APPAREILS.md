# Retours sur postes et tablettes (#PWA9)

Cette feuille aide à recueillir les retours. Elle n'est pas un jalon bloquant
pour faire évoluer l’application, publier ses évolutions ou démarrer des essais.
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

## Limites de la version maintenue

Depuis #PWA12 : 256 Mio décompressés, 5 000 entrées et 64 Mio pour la base ou
un fichier. Les médias et les ZIP restent sur OPFS ; SQLite et les images
traitées utilisent encore la mémoire. Ces bornes ne sont pas la capacité du
disque ni une garantie sur tablette. Le banc a transféré 2 300 photos/241 Mio ;
la PSS totale est distincte du tas WASM. Voir QUALIFICATION.md et PRODUCTION.md.

Un transfert peut prendre plusieurs minutes ; garder la page ouverte. Après
15 minutes sans réponse, le moteur est arrêté : rouvrir pour vérifier le dernier
état confirmé et ne pas répéter automatiquement une saisie. Les retours terrain
ne conditionnent pas la publication sur le périmètre qualifié.
