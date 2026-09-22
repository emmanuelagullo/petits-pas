import os
import dj_database_url
from pathlib import Path

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
VERSION_APPLICATION = os.environ.get("CARNET_VERSION", "").strip()

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

AUTH_USER_MODEL = "comptes.Utilisateur"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            "NAME": BASE_DIR / "carnet.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

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

# Limite de taille d'une photo de trace (5 Mo).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
