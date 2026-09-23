from django.conf import settings
from django.utils import timezone
from comptes.models import AffectationClasse

from .autorisations import ADMINISTRER_ECOLE, VOIR_CLASSE, autorise, classes_accessibles
from .contexte_ecole import ecole_courante


def session_ecole(request):
    utilisateur = request.user if request.user.is_authenticated else None
    ecole = ecole_courante(request) if utilisateur else None
    direction = bool(
        utilisateur
        and ecole
        and autorise(utilisateur, ADMINISTRER_ECOLE, ecole=ecole)
    )
    affectations_recentes = []
    affectations_passees = []
    if utilisateur and ecole:
        aujourd_hui = timezone.localdate()
        accessibles = set(
            classes_accessibles(utilisateur, VOIR_CLASSE, ecole).values_list(
                "pk", flat=True
            )
        )
        affectations = (
            AffectationClasse.objects.filter(
                appartenance__utilisateur=utilisateur,
                classe__ecole=ecole,
            )
            .select_related("classe")
            .order_by("-classe__annee_scolaire", "classe__ordre", "classe__nom")
        )
        for affectation in affectations:
            affectation.classe_accessible = affectation.classe_id in accessibles
            affectation.est_future = (
                affectation.etat == AffectationClasse.ACTIVE
                and affectation.date_debut > aujourd_hui
            )
            est_presente_ou_future = (
                affectation.etat == AffectationClasse.ACTIVE
                and (affectation.date_fin is None or affectation.date_fin >= aujourd_hui)
            )
            if est_presente_ou_future:
                affectations_recentes.append(affectation)
            else:
                affectations_passees.append(affectation)
    return {
        "ecole": ecole,
        "role": "direction" if direction else ("enseignant" if ecole else None),
        "est_direction": direction,
        "utilisateur_courant": utilisateur,
        "environnement_atelier": settings.ENVIRONNEMENT_ATELIER,
        "environnement_ephemere": settings.ENVIRONNEMENT_EPHEMERE,
        "version_application": settings.VERSION_APPLICATION,
        "email_disponible": settings.EMAIL_DISPONIBLE,
        "affectations_utilisateur_recentes": affectations_recentes,
        "affectations_utilisateur_passees": affectations_passees,
    }
