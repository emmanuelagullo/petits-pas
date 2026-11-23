"""Composition de définitions publiques, sans données de suivi."""
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence

from .paquets_referentiels import empaqueter


def catalogue_composition(versions):
    return {
        f"{version.pk}:{reference_competence(competence)}": (version, competence)
        for version in versions
        for competence in competences_document(version.contenu)
    }


def composer_paquet(catalogue, donnees, references):
    competences = []
    for reference in dict.fromkeys(references):
        if reference not in catalogue:
            raise ValidationError("Une compétence sélectionnée n’est plus disponible.")
        version, competence = catalogue[reference]
        origine = competence.get("source_origine", version.source.identifiant)
        if origine == donnees.get("identifiant"):
            raise ValidationError("Choisissez un identifiant différent des sources reprises.")
        competences.append({**competence, "source_origine": origine})

    if donnees.get("nouvelle"):
        competences.append({"identite": donnees.get("identite_nouvelle"), "libelle": donnees["nouvelle"],
                            "niveau": donnees.get("niveau_nouvelle")})
    for rang, competence in enumerate(competences, start=1):
        competence["code"] = f"C{rang}"
    source = {cle: donnees.get(cle) for cle in ("identifiant", "titre", "provenance", "licence")}
    return empaqueter({
        "format": 2, "source": {**source, "provisoire": True},
        "version": donnees.get("version"),
        "domaines": [{"code": "composition", "nom": donnees.get("rubrique"), "competences": competences}],
    })
