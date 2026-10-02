"""Profil navigateur expérimental, sans modification du profil serveur."""
from carnet.settings import *  # noqa: F403

MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("whitenoise.")]
STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
STATIC_URL = "/static/"
MEDIA_URL = "/app/media/"
FORCE_SCRIPT_NAME = "/app"
X_FRAME_OPTIONS = "SAMEORIGIN"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
DATABASES["default"]["OPTIONS"] = {"init_command": "PRAGMA journal_mode=DELETE"}
