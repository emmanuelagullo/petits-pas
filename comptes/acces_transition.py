"""Pont minimal entre le modèle #A2 et le moteur d'autorisation de #A3."""

from django.db.models import Q
from django.utils import timezone

from .models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole


def appartenances_actives(utilisateur, date=None):
    date = date or timezone.localdate()
    return (
        AppartenanceEcole.objects.a_la_date(date)
        .filter(
            utilisateur=utilisateur,
            utilisateur__is_active=True,
            ecole__etat="active",
        )
        .select_related("ecole")
    )


def appartenance_courante(request):
    appartenances = appartenances_actives(request.user)
    ecole_id = request.session.get("ecole_id")
    appartenance = appartenances.filter(ecole_id=ecole_id).first()
    if appartenance is None:
        appartenance = appartenances.order_by("ecole__nom", "ecole_id").first()
        if appartenance:
            request.session["ecole_id"] = appartenance.ecole_id
    return appartenance


def est_direction(appartenance, date=None):
    if appartenance is None:
        return False
    date = date or timezone.localdate()
    return ResponsabiliteEcole.objects.a_la_date(date).filter(
        appartenance=appartenance,
        type=ResponsabiliteEcole.DIRECTION,
    ).exists()


def a_une_affectation(appartenance, date=None):
    if appartenance is None:
        return False
    date = date or timezone.localdate()
    return (
        AffectationClasse.objects.a_la_date(date)
        .filter(
            appartenance=appartenance,
            classe__etat="active",
        )
        .filter(
            Q(appartenance__date_fin__isnull=True)
            | Q(appartenance__date_fin__gte=date)
        )
        .exists()
    )


def profil_compatible(appartenance):
    if est_direction(appartenance):
        return "direction"
    if a_une_affectation(appartenance):
        return "enseignant"
    return None
