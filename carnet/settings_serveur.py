"""Profil HTTPS volontaire #SOC6a ; le profil historique reste inchangé."""
import os
from django.core.exceptions import ImproperlyConfigured

if os.environ.get("CARNET_DEBUG") != "0":
    raise ImproperlyConfigured("Le profil serveur exige CARNET_DEBUG=0.")
from .settings import *  # noqa: F403
from pas_communs.serveur import configuration_https

if MODE_LOCAL:
    raise ImproperlyConfigured("Le profil serveur ne peut pas ouvrir un paquet autonome.")
try:
    globals().update(configuration_https(
        cle=SECRET_KEY, hotes=ALLOWED_HOSTS, origines=CSRF_TRUSTED_ORIGINS,
        proxy_https=os.environ.get("CARNET_PROXY_HTTPS", "non"),
        hsts=os.environ.get("CARNET_HSTS_SECONDES", "3600")))
except ValueError as erreur:
    raise ImproperlyConfigured(str(erreur)) from None
