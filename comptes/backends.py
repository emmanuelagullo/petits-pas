from django.core.exceptions import PermissionDenied

from .validators import LONGUEUR_MAX_MOT_DE_PASSE


class PlafondMotDePasse:
    """Refuse une saisie de mot de passe plus longue que le plafond.

    Ce backend n'authentifie personne : placé avant ModelBackend, il interrompt
    l'authentification si la saisie dépasse le plafond. Le backend standard reste
    inchangé, donc les sessions déjà ouvertes (qui mémorisent son chemin) restent
    valides.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if password is not None and len(password) > LONGUEUR_MAX_MOT_DE_PASSE:
            raise PermissionDenied
        return None

    # Pas de get_user() : ce backend n'authentifie personne et ne doit jamais
    # être celui qu'une session mémorise (force_login choisit le premier backend
    # qui en a un).
