"""Liens explicitement validés, sans inférence ni effet pédagogique automatique."""
from copy import deepcopy
from django.db.models import Q
from .models import CorrespondanceCompetence


def liens_actifs(ecole, annee, classe=None):
    perimetre = Q(classe__isnull=True)
    if classe is not None:
        perimetre |= Q(classe=classe)
    return CorrespondanceCompetence.objects.filter(perimetre, ecole=ecole,
        annee_scolaire=annee, active=True).order_by("pk")


def instantane_lien(lien):
    return {"id": lien.pk, "classe_id": lien.classe_id, "depart_id": lien.depart_id,
        "arrivee_id": lien.arrivee_id, "type_lien": lien.type_lien,
        "type_libelle": lien.get_type_lien_display(), "justification": lien.justification,
        "origine_depart": deepcopy(lien.origine_depart), "origine_arrivee": deepcopy(lien.origine_arrivee),
        "auteur_id": lien.auteur_id, "cree_le": lien.cree_le.isoformat(), "revision": lien.revision}


def correspondances_classe(classe, competence_id=None):
    from .referentiels import adoption_courante
    adoption = adoption_courante(classe)
    if adoption and adoption.clos:
        liens = deepcopy(adoption.etat_final.get("correspondances", []))
    else:
        liens = [instantane_lien(l) for l in liens_actifs(classe.ecole, classe.annee_scolaire, classe)]
    if competence_id is not None:
        liens = [l for l in liens if competence_id in (l["depart_id"], l["arrivee_id"])]
    return liens
