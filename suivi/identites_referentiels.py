"""Références de compétences dans un document de référentiel."""


def competences_document(contenu):
    for domaine in contenu.get("domaines", []):
        yield from domaine.get("competences", [])
        for sous in domaine.get("sous_domaines", []):
            yield from sous.get("competences", [])


def reference_competence(competence):
    origine = competence.get("source_origine")
    identifiant = competence["identite"]
    return f"{origine}/{identifiant}" if origine else identifiant


def references_suivi(ecole, version):
    from .models import CompetenceSourceEcole

    return {
        (identifiant if source_id == version.source_id else f"{source}/{identifiant}"): competence_id
        for source_id, source, identifiant, competence_id in CompetenceSourceEcole.objects.filter(
            ecole=ecole, identite__definitions__version=version
        ).values_list("identite__source_id", "identite__source__identifiant",
                      "identite__identifiant", "competence_id")
    }
