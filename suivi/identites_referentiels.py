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
        (identifiant if source_id == version.source_id else f"{diffusion or source}/{identifiant}"): competence_id
        for source_id, source, diffusion, identifiant, competence_id in CompetenceSourceEcole.objects.filter(
            ecole=ecole, identite__definitions__version=version
        ).values_list("identite__source_id", "identite__source__identifiant", "identite__source__identifiant_diffusion",
                      "identite__identifiant", "competence_id")
    }


def identifiant_source_ecole(ecole, identifiant):
    from hashlib import sha256

    return "catalogue-ecole-" + sha256(f"{ecole.pk}:{identifiant}".encode()).hexdigest()


def identifiant_diffusion(source):
    return source.identifiant_diffusion or source.identifiant
