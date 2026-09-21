from django.conf import settings

from comptes.acces_transition import (
    appartenance_courante,
    est_direction,
    profil_compatible,
)


def session_ecole(request):
    utilisateur = request.user if request.user.is_authenticated else None
    appartenance = appartenance_courante(request) if utilisateur else None
    ecole = appartenance.ecole if appartenance else None
    return {
        "ecole": ecole,
        "role": profil_compatible(appartenance),
        "est_direction": est_direction(appartenance),
        "utilisateur_courant": utilisateur,
        "environnement_atelier": settings.ENVIRONNEMENT_ATELIER,
        "environnement_ephemere": settings.ENVIRONNEMENT_EPHEMERE,
        "version_application": settings.VERSION_APPLICATION,
    }
