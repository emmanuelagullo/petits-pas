"""Préchargements limités aux listes de lecture, sans cache entre requêtes."""
from django.db.models import Prefetch

from .models import Scolarite


def avec_scolarites_pour_lecture(eleves):
    # Charger toutes les années : la scolarité courante reste la plus récente,
    # même lorsque la liste affichée appartient à une ancienne classe.
    return eleves.prefetch_related(Prefetch(
        "scolarites",
        queryset=Scolarite.objects.select_related("classe").order_by("-annee_scolaire"),
        to_attr="_scolarites_pour_lecture",
    ))
