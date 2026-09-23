from django.conf import settings

from .autorisations import ADMINISTRER_ECOLE, autorise
from .contexte_ecole import ecole_courante


def session_ecole(request):
    utilisateur = request.user if request.user.is_authenticated else None
    ecole = ecole_courante(request) if utilisateur else None
    direction = bool(
        utilisateur
        and ecole
        and autorise(utilisateur, ADMINISTRER_ECOLE, ecole=ecole)
    )
    return {
        "ecole": ecole,
        "role": "direction" if direction else ("enseignant" if ecole else None),
        "est_direction": direction,
        "utilisateur_courant": utilisateur,
        "environnement_atelier": settings.ENVIRONNEMENT_ATELIER,
        "environnement_ephemere": settings.ENVIRONNEMENT_EPHEMERE,
        "version_application": settings.VERSION_APPLICATION,
        "email_disponible": settings.EMAIL_DISPONIBLE,
    }
