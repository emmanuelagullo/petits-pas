# Profil serveur volontaire — #SOC6a

`carnet.settings_serveur` ajoute le contrat HTTPS de Pas communs 0.5.0. Le profil
historique `carnet.settings`, les lanceurs locaux et la PWA ne changent pas.
Aucune instance existante, notamment un hébergement en exploitation, ne bascule
sur ce nouveau profil par la seule installation du patch.

Le déployeur qui souhaite l'adopter explicitement définit :

```sh
export DJANGO_SETTINGS_MODULE=carnet.settings_serveur
export CARNET_DEBUG=0
# Même clé aléatoire stable qu'auparavant, depuis la configuration privée :
# CARNET_SECRET_KEY, CARNET_HOSTS, CARNET_CSRF_ORIGINS
python3 manage.py check --deploy
```

Lire DEPLOIEMENT.org pour base, SMTP, médias et exploitation. Ce profil exige
une clé d'au moins 50 caractères (sans prouver son aléa), des hôtes exacts et
origines HTTPS sans joker. Une clé existante insuffisante doit faire l'objet
d'une décision de rotation explicite ; ne pas en générer une à chaque démarrage.
Les origines n'ont pas de slash final ni chemin. Les noms de cookies, durées
de session, obligations 2FA, modèles, permissions et migrations sont conservés.

HTTPS, cookies Secure, anti-sniffing et interdiction d'iframe sont imposés.
HSTS vaut une heure sans sous-domaines/preload ; CARNET_HSTS_SECONDES accepte
0 à 31536000 secondes. Les recommandations Django ne sont pas masquées.
La valeur 0 est réservée à la préparation et produit un avertissement.

**Différence volontaire avec le profil historique :** X-Forwarded-Proto n'est
accepté que si CARNET_PROXY_HTTPS=oui. Avant de l'activer, réserver l'accès
backend au proxy et lui faire remplacer cet en-tête. Vérifier la chaîne TLS
réelle pour éviter boucle de redirection ou confiance à une entrée publique.
La confiance aux adresses clientes via CARNET_PROXYS_NB reste distincte, selon
DEPLOIEMENT.org ; aucun X-Forwarded-Host n'est adopté.

Le banc `python3 scripts/verifier-profil-serveur.py` prépare SQLite/statiques
fictifs dans un dossier temporaire, puis vérifie WSGI/Host/CSRF/cookies et le
proxy explicite. Il désactive les courriels dans cette seule fixture. Il ne
qualifie ni PostgreSQL, ni un certificat public, ni l'exploitation d'une école.
#SOC6b poursuivra les recettes CI et publication réutilisables.
