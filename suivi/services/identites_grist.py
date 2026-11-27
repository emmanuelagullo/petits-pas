"""Reconnaissance des classes dont le référentiel est déjà disponible localement."""
from suivi.models import PartageGristClasse

from .catalogues_externes import reference_classe_grist


def classes_grist_locales(ecole):
    return {
        f"classe-grist-{identifiant}": classe_id
        for identifiant, classe_id in PartageGristClasse.objects.filter(classe__ecole=ecole)
        .values_list("identifiant", "classe_id")
    }


def classe_grist_locale(ecole, reference):
    if reference_classe_grist(reference):
        return classes_grist_locales(ecole).get(reference)
    return None
