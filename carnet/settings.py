import os
from datetime import timedelta
from importlib.util import find_spec
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from .double_facteur import (
    lire_cles,
    lire_delai_grace,
    politique_deployeur_depuis_environnement,
)
from .version import version_application

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "CARNET_SECRET_KEY", "dev-seulement-a-changer-avant-toute-mise-en-ligne"
)
DEBUG = os.environ.get("CARNET_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("CARNET_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CARNET_CSRF_ORIGINS", "").split(",") if o
]
ENVIRONNEMENT_ATELIER = (
    os.environ.get("CARNET_ENVIRONNEMENT_ATELIER", "") == "oui"
)
ENVIRONNEMENT_EPHEMERE = (
    os.environ.get("CARNET_ENVIRONNEMENT_EPHEMERE", "") == "oui"
)
MODE_LOCAL = os.environ.get("CARNET_MODE_LOCAL", "") == "oui"
# Permission de sortie complète, accordée explicitement par l'exploitant.
def _ecoles_export(variable):
    valeur = os.environ.get(variable, "").strip()
    try:
        return ("*" if valeur == "*" else
                frozenset(int(v.strip()) for v in valeur.split(",") if v.strip()))
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"{variable} attend * ou des identifiants d'écoles séparés par des virgules.") from exc


EXPORT_ECOLES = _ecoles_export("CARNET_EXPORT_ECOLES")
EXPORT_CLASSES = _ecoles_export("CARNET_EXPORT_CLASSES")
DATABASE_ROUTERS = ["suivi.export_projection.RouteurProjection"]
EXPORT_ROOT = os.environ.get("CARNET_EXPORT_ROOT", "")
EXPORT_TAILLE_MAX = 10 * 1024**3
ESPACE_ESSAI = MODE_LOCAL and os.environ.get("CARNET_ESPACE_ESSAI", "") == "oui"
ESPACE_APERCU = MODE_LOCAL and os.environ.get("CARNET_ESPACE_APERCU", "") == "oui"
VERSION_APPLICATION = os.environ.get("CARNET_VERSION", "").strip() or version_application()
# Anti-bruteforce sur la connexion (django-axes). Actif par défaut, sauf pour
# l'installation autonome mono-poste (non exposée au réseau, et dont le paquet
# PyInstaller n'embarque pas axes). CARNET_ANTIBRUTEFORCE=oui|non surcharge.
ANTIBRUTEFORCE_ACTIF = (
    os.environ.get("CARNET_ANTIBRUTEFORCE", "non" if MODE_LOCAL else "oui")
    == "oui"
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "comptes",
    "suivi",
]

if ANTIBRUTEFORCE_ACTIF:
    INSTALLED_APPS.append("axes")

AUTH_USER_MODEL = "comptes.Utilisateur"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "suivi.acces_double_facteur.DoubleFacteurMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if ANTIBRUTEFORCE_ACTIF:
    # Recommandation django-axes : dernier middleware de la liste.
    MIDDLEWARE.append("axes.middleware.AxesMiddleware")
    # Le backend axes s'intercale devant le backend standard : il refuse
    # l'authentification tant que le couple adresse/identifiant est bloqué.
    AUTHENTICATION_BACKENDS = [
        "axes.backends.AxesStandaloneBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]

ROOT_URLCONF = "carnet.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "suivi.context.session_ecole",
            ],
        },
    },
]

WSGI_APPLICATION = "carnet.wsgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Les PaaS fournissent généralement l'accès à PostgreSQL sous la forme
    # d'une URL. L'application reste ainsi indépendante du fournisseur.
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Développement local et démonstration éphémère : aucune base externe
    # n'est nécessaire.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(
                os.environ.get("CARNET_SQLITE_PATH", BASE_DIR / "carnet.sqlite3")
            ),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = os.environ.get("CARNET_STATIC_URL", "static/")
STATIC_ROOT = Path(os.environ.get("CARNET_STATIC_ROOT", BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "referentiel" / "static"]

S3_BUCKET = os.environ.get("CARNET_S3_BUCKET")

if S3_BUCKET:
    DEFAULT_STORAGE = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": S3_BUCKET,
            "endpoint_url": os.environ.get("CARNET_S3_ENDPOINT_URL"),
            "region_name": os.environ.get("CARNET_S3_REGION"),
            "access_key": os.environ.get("CARNET_S3_ACCESS_KEY"),
            "secret_key": os.environ.get("CARNET_S3_SECRET_KEY"),
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": int(
                os.environ.get("CARNET_S3_URL_EXPIRATION", "300")
            ),
            "file_overwrite": False,
        },
    }
else:
    DEFAULT_STORAGE = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }

STORAGES = {
    "default": DEFAULT_STORAGE,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Render (comme la plupart des PaaS) termine le TLS en amont et transmet la
# requête en HTTP au conteneur : sans ceci, Django croit que tout est en
# clair et les cookies/CSRF se comportent mal derrière le proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("CARNET_FORCER_HTTPS", "") == "oui"

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("CARNET_MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# La session porte l'accès à l'école : on ne veut pas que la classe reste
# ouverte indéfiniment sur l'ordinateur du couloir.
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SAMESITE = "Lax"

# Seuil de mise en mémoire des requêtes et fichiers. La limite fonctionnelle
# des images privées (25 Mio avant normalisation) est contrôlée par le service
# médias ; au-delà de ce seuil, Django écrit déjà le téléversement sur disque.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --------------------------------------------------------------------------
# Envoi d'e-mail
# --------------------------------------------------------------------------
#
# Le transport est un choix explicite hors développement : backend SMTP natif
# de Django ou backend optionnel django-anymail. Un déploiement peut aussi
# assumer un mode sans courrier avec CARNET_EMAIL_DESACTIVE=oui.
#
EMAIL_BACKEND_CONFIGURE = os.environ.get("CARNET_EMAIL_BACKEND", "").strip()
EMAIL_DESACTIVE = os.environ.get("CARNET_EMAIL_DESACTIVE", "") == "oui"
if EMAIL_BACKEND_CONFIGURE and EMAIL_DESACTIVE:
    raise ImproperlyConfigured(
        "CARNET_EMAIL_BACKEND et CARNET_EMAIL_DESACTIVE=oui sont incompatibles."
    )

EMAIL_CONFIGURATION_EXPLICITE = bool(EMAIL_BACKEND_CONFIGURE or EMAIL_DESACTIVE)
EMAIL_DISPONIBLE = not EMAIL_DESACTIVE and bool(EMAIL_BACKEND_CONFIGURE or DEBUG)
EMAIL_BACKEND = EMAIL_BACKEND_CONFIGURE or (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.dummy.EmailBackend"
)

if EMAIL_BACKEND.startswith("anymail.backends."):
    if find_spec("anymail") is None:
        raise ImproperlyConfigured(
            "Un backend Anymail est configuré, mais django-anymail n'est pas "
            "installé. Installez requirements-anymail.txt ou choisissez le "
            "backend SMTP natif de Django."
        )
    INSTALLED_APPS.append("anymail")
EMAIL_HOST = os.environ.get("CARNET_EMAIL_HOTE", "localhost")
EMAIL_PORT = int(os.environ.get("CARNET_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("CARNET_EMAIL_UTILISATEUR", "")
EMAIL_HOST_PASSWORD = os.environ.get("CARNET_EMAIL_MOT_DE_PASSE", "")
EMAIL_USE_TLS = os.environ.get("CARNET_EMAIL_TLS", "oui") == "oui"
EMAIL_TIMEOUT = 10

DEFAULT_FROM_EMAIL = os.environ.get(
    "CARNET_EMAIL_EXPEDITEUR", "Petits Pas <ne-pas-repondre@petits-pas.example>"
)

# Configuration optionnelle Anymail : sans effet avec le backend SMTP natif.
ANYMAIL = {
    "SENDGRID_API_KEY": os.environ.get("CARNET_ANYMAIL_SENDGRID_CLE", ""),
    "MAILGUN_API_KEY": os.environ.get("CARNET_ANYMAIL_MAILGUN_CLE", ""),
    "MAILGUN_SENDER_DOMAIN": os.environ.get("CARNET_ANYMAIL_MAILGUN_DOMAINE", ""),
    "POSTMARK_SERVER_TOKEN": os.environ.get("CARNET_ANYMAIL_POSTMARK_JETON", ""),
    "BREVO_API_KEY": os.environ.get("CARNET_ANYMAIL_BREVO_CLE", ""),
}

# Adresse IP des clients derrière un reverse-proxy (voir DEPLOIEMENT.org).
# 0 (défaut) : seule REMOTE_ADDR est lue, comportement inchangé. N > 0 :
# l'application est derrière N proxys de confiance qui complètent chacun
# X-Forwarded-For ; le client est alors la N-ième entrée en partant de la
# droite (carnet/reseau.py). N doit être EXACTEMENT le nombre de proxys de
# confiance : trop petit, on voit l'adresse d'un proxy (perte de finesse, sans
# danger) ; trop grand, on lit une entrée que le client a pu forger en
# préfixant l'en-tête (blocage contournable). À vérifier avec la procédure de
# DEPLOIEMENT.org.
PROXYS_DE_CONFIANCE = max(0, int(os.environ.get("CARNET_PROXYS_NB", "0")))
# Politique de 2FA du déployeur : obligatoire jusqu'à un rang de fonction,
# désactivée à partir d'un rang (voir AUDIT-AUTHENTIFICATION-INVITATIONS.org,
# § 6.7). Lue et validée ici ; l'exigence n'est pas encore appliquée.
(
    DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG,
    DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG,
) = politique_deployeur_depuis_environnement(os.environ, mode_local=MODE_LOCAL)
DOUBLE_FACTEUR_DELAI_GRACE_JOURS = lire_delai_grace(os.environ)
DOUBLE_FACTEUR_CLES = lire_cles(os.environ)
DOUBLE_FACTEUR_EMETTEUR = "Petits Pas"
# Dépendances facultatives (requirements-2fa.txt) : sans elles, ou sans clé de
# chiffrement, ou en mode local, la fonction est indisponible et rien ne
# change pour personne.
DOUBLE_FACTEUR_DEPENDANCES = all(
    find_spec(nom) is not None for nom in ("cryptography", "qrcode", "django_otp")
)
DOUBLE_FACTEUR_DISPONIBLE = (
    not MODE_LOCAL and DOUBLE_FACTEUR_DEPENDANCES and bool(DOUBLE_FACTEUR_CLES)
)
if not MODE_LOCAL and (DOUBLE_FACTEUR_CLES or DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG > 0):
    # Comme pour Anymail : une demande explicite que rien ne peut satisfaire
    # empêche le démarrage plutôt que de laisser croire qu'elle s'applique.
    if not DOUBLE_FACTEUR_DEPENDANCES:
        raise ImproperlyConfigured(
            "Le 2FA est demandé (CARNET_2FA_CLE ou CARNET_2FA_OBLIGATOIRE) mais "
            "ses dépendances ne sont pas installées. Installez requirements-2fa.txt."
        )
    if not DOUBLE_FACTEUR_CLES:
        raise ImproperlyConfigured(
            "CARNET_2FA_OBLIGATOIRE exige une clé de chiffrement : renseignez "
            "CARNET_2FA_CLE (voir DEPLOIEMENT.org)."
        )
    from cryptography.fernet import Fernet

    for _cle in DOUBLE_FACTEUR_CLES:
        try:
            Fernet(_cle)
        except (ValueError, TypeError) as erreur:
            raise ImproperlyConfigured(
                "CARNET_2FA_CLE contient une clé invalide : elle doit être une "
                "clé Fernet (32 octets en base64 URL-safe)."
            ) from erreur
# Durée pendant laquelle l'exigence d'un compte est conservée en session
# avant d'être recalculée (secondes).
DOUBLE_FACTEUR_CACHE_SECONDES = 60
RATELIMIT_DOUBLE_FACTEUR = os.environ.get("CARNET_RATELIMIT_DOUBLE_FACTEUR", "5/15m")
RATELIMIT_DOUBLE_FACTEUR_IP = os.environ.get("CARNET_RATELIMIT_DOUBLE_FACTEUR_IP", "30/15m")
AXES_CLIENT_IP_CALLABLE = "carnet.reseau.adresse_client"

# --------------------------------------------------------------------------
# Anti-bruteforce sur la connexion
# --------------------------------------------------------------------------
#
# Seuils différenciés par déploiement (voir
# AUDIT-AUTHENTIFICATION-INVITATIONS.org, §3.5) : plus souples sur la
# démonstration publique éphémère (visiteurs multiples, données fictives),
# plus stricts dès que des données réelles d'école sont en jeu.
# CARNET_CONNEXION_* surcharge explicitement ces valeurs par déploiement.
AXES_FAILURE_LIMIT = int(
    os.environ.get(
        "CARNET_CONNEXION_TENTATIVES_MAX", "10" if ENVIRONNEMENT_EPHEMERE else "5"
    )
)
AXES_COOLOFF_TIME = timedelta(
    minutes=int(
        os.environ.get(
            "CARNET_CONNEXION_BLOCAGE_MINUTES", "5" if ENVIRONNEMENT_EPHEMERE else "15"
        )
    )
)
# Le blocage porte sur le couple adresse + identifiant : un incident sur un
# poste partagé (salle des maîtres) ne bloque pas les autres comptes qui s'y
# connectent, et un identifiant ciblé reste freiné depuis chaque adresse.
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_TEMPLATE = "suivi/connexion_bloquee.html"

# --------------------------------------------------------------------------
# Limitation de fréquence des demandes de réinitialisation de mot de passe
# --------------------------------------------------------------------------
#
# django-axes protège la connexion (succès/échec d'authentification), mais
# la demande de réinitialisation ne s'authentifie jamais : rien n'y limitait
# la fréquence des envois, ouvrant un risque de nuisance (bombardement
# d'e-mails vers une adresse qu'on ne possède pas), pas de fuite de compte
# (PasswordResetForm ne révèle jamais si l'adresse existe). django-ratelimit
# comble ce point précis, sans dépendre de django-axes conçu pour des
# tentatives d'authentification, pas un simple comptage de requêtes.
#
# django-ratelimit utilise le cache Django par défaut, ici la mémoire locale
# du processus (aucun cache partagé n'est configurable aujourd'hui) : les
# compteurs repartent de zéro au redémarrage et ne sont pas partagés entre
# workers gunicorn (un seul par défaut). Suffisant pour un frein de nuisance,
# pas une garantie stricte multi-worker.
RATELIMIT_MOT_DE_PASSE_OUBLIE = os.environ.get(
    "CARNET_RATELIMIT_MOT_DE_PASSE_OUBLIE", "5/h"
)
# Changement de mot de passe d'un compte connecté : la vérification de
# l'ancien mot de passe (check_password) ne passe pas par authenticate(),
# donc django-axes ne la voit pas. Ce plafond, par compte, empêche une
# session détournée de deviner l'ancien mot de passe sans frein.
RATELIMIT_CHANGEMENT_MOT_DE_PASSE = os.environ.get(
    "CARNET_RATELIMIT_CHANGEMENT_MOT_DE_PASSE", "10/h"
)

# Fichier facultatif écrit par l’exploitant ; aucune donnée personnelle.
MAINTENANCE_ANNONCE = os.environ.get("CARNET_MAINTENANCE_ANNONCE", "")
