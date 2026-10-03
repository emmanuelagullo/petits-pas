"""Profil navigateur expérimental, sans modification du profil serveur."""
from carnet.settings import *  # noqa: F403

MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
STORAGES["default"] = {"BACKEND": "pwa.media_storage.LocalMediaStorage"}
STATIC_URL = "/static/"
MEDIA_URL = "/app/media/"
FORCE_SCRIPT_NAME = "/app"
X_FRAME_OPTIONS = "SAMEORIGIN"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Les cookies virtuels disparaissent à chaque fermeture ; conserver la durée
# maximale de session, sans réécrire son échéance à chaque simple lecture.
SESSION_SAVE_EVERY_REQUEST = False
DATABASES["default"]["OPTIONS"] = {"init_command": "PRAGMA journal_mode=DELETE"}

MODE_PWA = True
ROOT_URLCONF = "pwa.urls"
TEMPLATES[0]["OPTIONS"]["context_processors"].append("pwa.views.contexte")
DATA_UPLOAD_MAX_MEMORY_SIZE = 70 * 1024**2

TEMPLATES[0]["DIRS"].insert(0, BASE_DIR / "pwa/templates")
