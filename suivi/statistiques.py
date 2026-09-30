"""Comptages du suivi sans chargement des observations individuelles."""
from django.db.models import Count, Q

from .models import Observation
from .referentiels import observations_classe


def repartition_competences(classe, competences):
    """Au plus trois requêtes, quel que soit le nombre de compétences.

    Les états actuels sont ceux de la saisie de classe : une réussite
    conservée d'une année précédente compte également comme une réussite.
    Les élèves archivés et les inscriptions dans d'autres classes sont exclus.
    """
    competences = list(competences)
    eleves = classe.eleves.filter(ecole_id=classe.ecole_id)
    total = eleves.count()
    comptes = {
        ligne["competence_id"]: ligne
        for ligne in (observations_classe(classe).filter(
            eleve_id__in=eleves.values("pk"),
            competence_id__in=[c.pk for c in competences],
        ).order_by().values("competence_id").annotate(
            reussites=Count("pk", filter=Q(statut_lecture=Observation.REUSSI)),
            en_cours=Count("pk", filter=Q(statut_lecture=Observation.EN_COURS)),
            inconnus=Count("pk", filter=Q(connu_lecture=False) | Q(connu_lecture__isnull=True)),
        ))
    }
    for competence in competences:
        compte = comptes.get(competence.pk, {})
        reussites = compte.get("reussites", 0)
        en_cours = compte.get("en_cours", 0)
        inconnus = compte.get("inconnus", 0)
        reste = total - reussites - en_cours - inconnus
        competence.repartition = {
            "total": total, "reussites": reussites, "en_cours": en_cours,
            "non_observes": reste, "etats_inconnus": inconnus,
        }
    return total
