"""Transformations d'une édition portable, sans accès au suivi des élèves."""
from copy import deepcopy
from uuid import uuid4

from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence
from suivi.services.import_sources_referentiels import normaliser


def rubriques_equipe(document):
    for rubrique in document["domaines"]:
        yield rubrique["code"], rubrique["nom"], rubrique
        for sous in rubrique.get("sous_domaines", []):
            yield f"{rubrique['code']}/{sous['code']}", f"{rubrique['nom']} › {sous['nom']}", sous


def modifier_edition_equipe(base, action, donnees):
    document = deepcopy(base)
    rubriques = {cle: rubrique for cle, _, rubrique in rubriques_equipe(document)}
    if action == "ajouter-competence":
        cible = rubriques.get(donnees.get("rubrique"))
        if cible is None:
            raise ValidationError("Choisissez une rubrique du référentiel.")
        identite = uuid4().hex
        cible.setdefault("competences", []).append({
            "identite": f"equipe-{identite}", "code": "E" + identite[:19],
            "libelle": donnees.get("libelle", "").strip(), "niveau": donnees.get("niveau", "PS"),
        })
    else:
        for rubrique in rubriques.values():
            competences = rubrique.get("competences", [])
            choix = next((c for c in competences if reference_competence(c) == donnees.get("reference")), None)
            if choix is not None:
                if action == "retirer-competence":
                    competences.remove(choix)
                elif action == "modifier-competence":
                    choix["libelle"] = donnees.get("libelle", "").strip()
                    choix["niveau"] = donnees.get("niveau", "")
                break
        else:
            raise ValidationError("Cette compétence ne figure plus dans cette édition.")
    if document == base:
        return document
    document["structure_seule"] = not any(competences_document(document))
    document["version"] = f"edition-{uuid4().hex}"
    normaliser(document)
    return document
