"""Références de compétences dans un document de référentiel."""
import re
from base64 import urlsafe_b64decode
from uuid import UUID


def est_uuid_portable(valeur):
    if not re.fullmatch(r"pp-[A-Za-z0-9_-]{21}[AQgw]", valeur):
        return False
    return UUID(bytes=urlsafe_b64decode(valeur[3:] + "==")).version == 4


def competences_document(contenu):
    for domaine in contenu.get("domaines", []):
        yield from domaine.get("competences", [])
        for sous in domaine.get("sous_domaines", []):
            yield from sous.get("competences", [])


def reference_competence(competence):
    origine = competence.get("source_origine")
    identifiant = competence["identite"]
    return f"{origine}/{identifiant}" if origine and not est_uuid_portable(identifiant) else identifiant


def references_suivi(ecole, version):
    from .models import CompetenceSourceEcole

    return {
        reference_competence({"identite": identifiant, "source_origine":
                              "" if source_id == version.source_id else diffusion or source}): competence_id
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


def identifiant_source_classe(classe, identifiant):
    from hashlib import sha256

    return "catalogue-classe-" + sha256(f"{classe.pk}:{identifiant}".encode()).hexdigest()
