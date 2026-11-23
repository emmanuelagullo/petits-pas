"""Sources consultables et ajout d'une définition au suivi de classe."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.identites_referentiels import reference_competence, references_suivi
from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, VOIR_SUIVI, autorise
from suivi.models import AdaptationCompetence, Classe, CompetenceLocale
from suivi.referentiels import adoption_courante, contenu_adoption, contenu_origine
from .ajouts_referentiels import _verrouiller, catalogue_reprises, reprendre_ajout
from .choix_bases_referentiels import _application_verrouillee, choix_bases
from .versions_sources_ecoles import definir_version_ecole


def sources_catalogue(utilisateur, classe, adoption):
    sources = {}
    for version in choix_bases(classe.ecole, classe.annee_scolaire).versions:
        if version.pk != adoption.version_id:
            sources[f"version-{version.pk}"] = (str(version.source.titre) + f" · {version.numero}", version, None)
    for autre in Classe.objects.filter(ecole=classe.ecole, annee_scolaire__lte=classe.annee_scolaire
                                        ).exclude(pk=classe.pk).order_by("-annee_scolaire", "nom", "pk"):
        if not autorise(utilisateur, VOIR_SUIVI, autre):
            continue
        autre_adoption = adoption_courante(autre)
        if autre_adoption:
            sources[f"classe-{autre.pk}"] = (f"{autre.nom} · {autre.annee_scolaire}", None, autre_adoption)
    return sources


def lignes_source(version, adoption, *, utilisateur, classe):
    if version and version.contenu.get("origine") == "source_declaree":
        for domaine in version.contenu["domaines"]:
            for c in domaine["competences"]:
                yield reference_competence(c), c, domaine["nom"], ""
            for sous in domaine["sous_domaines"]:
                for c in sous["competences"]:
                    yield reference_competence(c), c, domaine["nom"], sous["nom"]
        return
    contenu = version.contenu if version else contenu_adoption(adoption)
    domaines = {d["id"]: d["nom"] for d in contenu.get("domaines", [])}
    sous_domaines = {d["id"]: d["nom"] for d in contenu.get("sous_domaines", [])}
    reprises = set(catalogue_reprises(utilisateur=utilisateur, ecole=classe.ecole,
        annee=classe.annee_scolaire, classe=classe).values_list("competence_id", flat=True))
    exclus = set(CompetenceLocale.objects.filter(ecole=classe.ecole).exclude(
        competence_id__in=reprises).values_list("competence_id", flat=True))
    for c in contenu.get("competences", []):
        if c["active"] and c["id"] not in exclus:
            yield str(c["id"]), c, domaines[c["domaine_id"]], sous_domaines.get(c["sous_domaine_id"], "")


def competence_id_source(classe, version, reference, candidat):
    if not version or version.contenu.get("origine") != "source_declaree":
        return candidat["id"]
    return references_suivi(classe.ecole, version).get(reference)


def extrait(contenu, ligne):
    return {
        "domaines": [d for d in contenu["domaines"] if d["id"] == ligne["domaine_id"]],
        "sous_domaines": [s for s in contenu.get("sous_domaines", []) if s["id"] == ligne["sous_domaine_id"]],
        "competences": [ligne],
        "formulations": [f for f in contenu.get("formulations", []) if f["competence_id"] == ligne["id"]],
    }


@transaction.atomic
def ajouter_depuis_source(*, utilisateur, classe, source, reference, adoption_attendue, revision_attendue=None):
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    _application_verrouillee(classe.annee_scolaire)
    adoption = _verrouiller(utilisateur, classe.ecole, classe.annee_scolaire, classe, adoption_attendue)
    choix = sources_catalogue(utilisateur, classe, adoption).get(source)
    if choix is None:
        raise PermissionDenied
    _, version, autre = choix
    candidate = next((c for ref, c, _, _ in lignes_source(version, autre, utilisateur=utilisateur, classe=classe) if ref == reference), None)
    if candidate is None:
        raise ValidationError("Cette compétence n’est plus disponible dans la source choisie.")
    if version:
        contenu = definir_version_ecole(classe.ecole, version)
        if version.contenu.get("origine") == "source_declaree":
            identifiant = references_suivi(classe.ecole, version)[reference]
            ligne = next(c for c in contenu["competences"] if c["id"] == identifiant)
        else:
            ligne = candidate
    else:
        contenu = contenu_adoption(autre)
        ligne = candidate
    revision = AdaptationCompetence.objects.filter(classe=classe, competence_id=ligne["id"]
        ).values_list("revision", flat=True).first() or 0
    if revision_attendue is not None and revision != revision_attendue:
        raise ValidationError("Le suivi a changé. Rechargez le formulaire de sélection.")
    locale = CompetenceLocale.objects.filter(ecole=classe.ecole, competence_id=ligne["id"]).first()
    if locale:
        reprendre_ajout(utilisateur=utilisateur, ecole=classe.ecole, annee=classe.annee_scolaire,
                       classe=classe, locale=locale, adoption_attendue=adoption.pk)
        return locale.competence
    regle, _ = AdaptationCompetence.objects.get_or_create(classe=classe, competence_id=ligne["id"],
        defaults={"ecole": classe.ecole, "annee_scolaire": classe.annee_scolaire})
    dans_base = any(c["id"] == ligne["id"] for c in contenu_origine(adoption).get("competences", []))
    if not dans_base and not regle.ajout:
        regle.ajout = extrait(contenu, ligne)
    regle.visible = True
    regle.revision += 1
    regle.full_clean()
    regle.save()
    journaliser(utilisateur, "referentiel.competence_reprise", regle,
                nouvelles={"version": (version or autre.version).pk, "classe_source": autre.classe_id if autre else None})
    return regle.competence
