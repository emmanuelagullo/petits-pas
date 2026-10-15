"""Paramètres rapides, à sélectionner explicitement pour les tests Django.

Ne pas utiliser pour servir l'application ni pour construire une distribution.
Les sous-processus d'export conservent leurs paramètres ordinaires.
"""

from django.conf.global_settings import PASSWORD_HASHERS as HASHERS_DJANGO

from .settings import *  # noqa: F403


# Seuls les mots de passe fictifs nouvellement créés utilisent MD5. Garder les
# lecteurs ordinaires pour vérifier les archives et mots de passe existants.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", *HASHERS_DJANGO]
