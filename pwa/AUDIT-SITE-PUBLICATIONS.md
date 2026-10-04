# Prompt pour le prochain chat : site public et publications (#PWA10)

Je travaille sur Petits Pas, une application libre Django/HTMX pour les équipes
pédagogiques de maternelle. Dépôt de référence public :
https://gitlab.inria.fr/petits-pas/petits-pas ; miroir :
https://github.com/emmanuelagullo/petits-pas. Documentation Hugo :
https://petits-pas.gitlabpages.inria.fr/petits-pas/ ; démonstration partagée,
jetable, sur https://petits-pas.onrender.com/ ; prototype navigateur :
https://petits-pas.gitlabpages.inria.fr/petits-pas-pwa/.

Lis AGENTS.md, README.md, CONTRIBUTING.md, site/README.md, pwa/README.md,
pwa/PUBLICATION.md et les sources actuelles sur main. Distingue le code livré,
les publications effectives et les essais réellement réalisés. Toute contribution
au dépôt doit être livrée comme patch git am, sur main récent, au nom de
Emmanuel Agullo <emmanuel.agullo@inria.fr>, sans signed-off.

Je souhaite un audit puis une évolution du site Hugo et des publications :

- Proposer une rubrique de premier niveau, voisine du Guide pratique, pour
  choisir comment démarrer ; trouver un intitulé simple, p. ex. « Démarrer ».
- Mettre les usages locaux au premier plan ou au moins à égalité : application
  dans le navigateur, programme Windows/Linux à télécharger. Expliquer leurs
  possibilités et limites réelles, sauvegardes, transfert ZIP et impression.
- Présenter simplement le mode hébergé partagé : essayer la démonstration Render
  avec données fictives, puis se renseigner auprès de l'école si un service a
  déjà été déployé. Sinon, indiquer le chemin de déploiement pour une institution
  ou une personne compétente. Éviter « client-serveur » dans les parcours enseignants.
- Rendre faciles à trouver les informations de protection des données, fiche
  destinée aux parents si disponible, démarches de mise en service, rôles et
  responsabilités. Ne pas inventer un accord RGPD ni présenter le mode local
  comme dispensé de protection des données. Distinguer logiciel ouvert et
  données privées. Ne pas publier de notes ou paramètres privés d'hébergement.
- Auditer l'ensemble des entrées, navigation, Guide pratique, inventaire, fiches
  de téléchargement et pages pour les institutions ; proposer une organisation
  cohérente et supprimer les contradictions/doublons, sans jargon.
- Auditer et homogénéiser autant que pertinent les publications PWA et autonome.
  Le clic manuel « pwa-publication » après réussite de « pwa-prototype » est
  apprécié. Étudier un principe similaire pour les binaires, les tags communs,
  la traçabilité des versions et artefacts, les mises à jour et leur récupération.
  Faire des propositions concrètes avant de toucher aux règles de release.

État technique à vérifier dans les sources : runtime Pyodide/Django dans un
Worker, Service Worker sous /petits-pas-pwa/, données locales OPFS/IndexedDB,
ZIP communs PWA et autonome, impression navigateur en PWA ; aucune
synchronisation entre appareils. #PWA7–8 ajoutent installation proposée selon
le navigateur, étapes de démarrage, version, aide d'erreur, accès aux sauvegardes
et date du dernier ZIP préparé/rappel après sept jours dans les modes locaux.
Cette date ne prouve pas qu'une copie a été conservée hors appareil. Limite
actuelle 64 Mio avant compression : base et médias encore en mémoire ; ce n'est
pas une limite OPFS. Les essais terrain sont une feuille non bloquante
(pwa/ESSAIS-APPAREILS.md) : consolider avec les bancs disponibles puis ajuster
avec les retours, sans prétendre que toutes les tablettes sont validées.

Commence par un audit court avec une proposition de navigation et une feuille
de route. Progressons ensuite vers une mise en œuvre : vocabulaire simple,
parcours par intention, explicitation des conséquences d'une restauration,
sauvegarde indépendante de l'appareil, versions réellement disponibles.
Ne pas exiger de refaire #PWA7–8 avant cet audit ; vérifier leurs changements
sur main et traiter les écarts éventuels comme des constats.
