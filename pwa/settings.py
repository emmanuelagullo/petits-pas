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

MODE_PWA = True
ROOT_URLCONF = "pwa.urls"
TEMPLATES[0]["OPTIONS"]["context_processors"].append("pwa.views.contexte")
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024**2

TEMPLATES[0]["DIRS"].insert(0, BASE_DIR / "pwa/templates")
