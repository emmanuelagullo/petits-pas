"""Composition en lecture des ajouts retenus ; aucune modification des sources."""
from copy import deepcopy
from .models import DisponibiliteCompetenceLocale


def contenu_avec_ajouts(contenu, classe):
    resultat = deepcopy(contenu)
    for choix in DisponibiliteCompetenceLocale.objects.filter(classe=classe,
            annee_scolaire=classe.annee_scolaire, locale__ecole_id=classe.ecole_id).select_related("locale").order_by("pk"):
        for rubrique in ("domaines", "competences"):
            ids = {c["id"] for c in resultat.setdefault(rubrique, [])}
            resultat[rubrique].extend(deepcopy(c) for c in choix.locale.definition[rubrique] if c["id"] not in ids)
    return resultat
