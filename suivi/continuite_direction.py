"""Continuité des droits de gestion, y compris après les échéances prévues."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from comptes.models import ResponsabiliteEcole


def verifier_continuite_direction(ecole_id, *, exclure=None, modification=None):
    """Exiger une couverture continue à partir d'aujourd'hui, sans fin prévue.

    Une modification de compte, appartenance ou responsabilité est projetée
    sans l'enregistrer. Les écritures appelantes verrouillent d'abord l'école.
    Les écritures SQL directes restent du ressort de l'exploitation.
    """
    aujourd_hui = timezone.localdate()
    periodes = []
    for responsabilite in ResponsabiliteEcole.objects.filter(
        appartenance__ecole_id=ecole_id, type=ResponsabiliteEcole.DIRECTION
    ).select_related("appartenance__utilisateur"):
        if responsabilite.pk == exclure:
            continue
        appartenance = responsabilite.appartenance
        utilisateur = appartenance.utilisateur
        if modification is not None:
            if isinstance(modification, ResponsabiliteEcole) and modification.pk == responsabilite.pk:
                responsabilite = modification
                appartenance = responsabilite.appartenance
                utilisateur = appartenance.utilisateur
            elif modification._meta.model_name == "appartenanceecole" and modification.pk == appartenance.pk:
                appartenance = modification
                utilisateur = appartenance.utilisateur
            elif modification._meta.model_name == "utilisateur" and modification.pk == utilisateur.pk:
                utilisateur = modification
        if (not utilisateur.is_active or appartenance.etat != "active"
                or responsabilite.etat != "active"
                or responsabilite.type != ResponsabiliteEcole.DIRECTION):
            continue
        debut = max(appartenance.date_debut, responsabilite.date_debut)
        fins = [d for d in (appartenance.date_fin, responsabilite.date_fin) if d]
        fin = min(fins) if fins else None
        if fin is None or fin >= debut:
            periodes.append((debut, fin))
    prochain = aujourd_hui
    for debut, fin in sorted(periodes, key=lambda p: p[0]):
        if debut > prochain:
            break
        if fin is None:
            return
        if fin >= prochain:
            # date.max peut apparaître dans une ancienne configuration.
            if fin.year == 9999:
                continue
            prochain = fin + timedelta(days=1)
    raise ValidationError(
        "L'école doit conserver une personne autorisée à la gérer, "
        "sans interruption ni fin prévue. Accordez d'abord ces droits "
        "à une autre personne."
    )
