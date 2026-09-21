from django.conf import settings

from .models import Ecole


def session_ecole(request):
    utilisateur = request.user if request.user.is_authenticated else None
    ecole_id = utilisateur.ecole_id if utilisateur else None
    ecole = Ecole.objects.filter(pk=ecole_id).first() if ecole_id else None
    return {
        "ecole": ecole,
        "role": utilisateur.profil_transition if utilisateur else None,
        "est_direction": utilisateur.est_direction if utilisateur else False,
        "utilisateur_courant": utilisateur,
        "environnement_atelier": settings.ENVIRONNEMENT_ATELIER,
        "environnement_ephemere": settings.ENVIRONNEMENT_EPHEMERE,
        "version_application": settings.VERSION_APPLICATION,
    }
