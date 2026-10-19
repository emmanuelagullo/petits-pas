# Paquet historique fictif

`paquet-local-avant-soc2.zip` est produit par `suivi.paquet_local` du commit
`fec9707` de Petits Pas, avant extraction #SOC2. Il contient uniquement une
table de migrations minimale, une clé explicitement fictive et des octets de
média fictifs. Son manifeste n’a pas de champ `application`. Le test garantit
la reprise du format historique par le moteur partagé. Ne pas régénérer
cette archive avec le nouveau moteur : conserver ce témoin de compatibilité.


## École représentative 0.10

`ecole-fictive-0.10.zip` vient du générateur `scripts/construire-ecole-fictive.py`
du tag 0.10 (`fec9707b28df13115e22be6f894e0abc430390cc`). Dans une copie
intermédiaire, trois photos synthétiques de 24×16 pixels (JPEG, PNG, WebP)
ont été liées à trois traces ; l'export final a été fait par le moteur de ce
même tag, avant extraction SOC2. Aucun code du socle n'a produit ce témoin.
La copie intermédiaire est distincte du ZIP initial, dont le SHA-256 est resté
inchangé. Le manifeste historique ne contient pas `application`.

La notice JSON conserve l'origine, l'empreinte et les comptes attendus : une
école, 14 classes, 64 élèves fictifs, 1 341 compétences, 747 observations,
173 traces, 9 comptes et 3 médias, dont des chemins avec espaces et accents.
Les noms, dates et identifiants sont fictifs ; la clé est publique et fictive.
Ne pas régénérer ce témoin avec le nouveau moteur.

`test_archive_historique.py` restaure dans un dossier temporaire, exporte avec
le wheel actuellement adopté, restaure ce nouvel export puis lance les
migrations actuelles sur cette seconde copie. Il compare le contenu SQL,
les empreintes de la clé et des médias, et recontrôle le ZIP d'origine.
Le test est lancé dans les matrices Django GitLab et bureau Windows/Linux.

Cette fixture ne démontre pas la reprise de toutes les archives d'utilisateurs.
Aucun essai sur données réelles n'a été réalisé pour cette qualification. Un
éventuel essai d'exploitation doit porter sur une copie privée hors Git, dans
un dossier indépendant, service arrêté si la copie vient d'un paquet actif.
Conserver l'original et vérifier son empreinte avant/après ; ne publier ni ZIP,
ni identités, ni capture, ni rapport contenant des données réelles.
