"""Lecture du référentiel commune aux saisies, réglages et carnets."""
from django.db.models import Prefetch

from .models import Competence, Domaine


def arbre_competences(ecole, niveaux=None):
    competences = (Competence.objects.filter(active=True)
                   .select_related("sous_domaine", "domaine__ecole")
                   .order_by("ordre", "pk"))
    if niveaux:
        competences = competences.filter(niveau__in=niveaux)
    return Domaine.objects.filter(ecole=ecole).order_by("ordre", "pk").prefetch_related(
        Prefetch("competences", queryset=competences, to_attr="visibles"),
        "attendus",
    )
