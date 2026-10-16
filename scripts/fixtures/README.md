# Paquet historique fictif

`paquet-local-avant-soc2.zip` est produit par `suivi.paquet_local` du commit
`fec9707` de Petits Pas, avant extraction #SOC2. Il contient uniquement une
table de migrations minimale, une clé explicitement fictive et des octets de
média fictifs. Son manifeste n’a pas de champ `application`. Le test garantit
la reprise du format historique par le moteur partagé. Ne pas régénérer
cette archive avec le nouveau moteur : conserver ce témoin de compatibilité.
