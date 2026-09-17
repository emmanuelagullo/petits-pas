from django.conf import settings

from .models import Ecole


def session_ecole(request):
    ecole_id = request.session.get("ecole_id")
    ecole = Ecole.objects.filter(pk=ecole_id).first() if ecole_id else None
    return {
        "ecole": ecole,
        "role": request.session.get("role"),
        "est_direction": request.session.get("role") == "direction",
        "environnement_atelier": settings.ENVIRONNEMENT_ATELIER,
        "environnement_ephemere": settings.ENVIRONNEMENT_EPHEMERE,
        "version_application": settings.VERSION_APPLICATION,
    }
