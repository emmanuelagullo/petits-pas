"""Sources consultables et ajout d'une définition au suivi de classe."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.identites_referentiels import references_suivi
from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, autorise
from suivi.models import AdaptationCompetence, Classe, CompetenceLocale, VersionReferentiel
from suivi.referentiels import adoption_courante, contenu_origine
from .ajouts_referentiels import _verrouiller, catalogue_reprises, reprendre_ajout
from .choix_bases_referentiels import _application_verrouillee, choix_bases
from .versions_sources_ecoles import definir_version_ecole
from .partage_referentiel_classe import contenu_commun_classe
from .apercu_mises_a_jour import definitions_document


def sources_catalogue(utilisateur, classe, adoption):
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    sources = {}
    versions = {v.pk: v for v in choix_bases(classe.ecole, classe.annee_scolaire).versions}
    versions.update({v.pk: v for v in VersionReferentiel.objects.filter(
        source__ecole=classe.ecole, contenu__origine="source_declaree"
    ).select_related("source").order_by("source__titre", "pk")})
    for version in versions.values():
        if version.pk != adoption.version_id:
            sources[f"version-{version.pk}"] = (str(version.source.titre) + f" · {version.numero}", version, None)
    for autre in Classe.objects.filter(ecole=classe.ecole, etat=Classe.ACTIVE,
                                        annee_scolaire__lte=classe.annee_scolaire
                                        ).exclude(pk=classe.pk).order_by("-annee_scolaire", "nom", "pk"):
        autre_adoption = adoption_courante(autre)
        if autre_adoption:
            sources[f"classe-{autre.pk}"] = (f"{autre.nom} · {autre.annee_scolaire}", None, autre_adoption)
    return sources


def lignes_source(version, adoption, *, utilisateur, classe):
    if version and version.contenu.get("origine") == "source_declaree":
        for reference, c in definitions_document(version.contenu).items():
            yield reference, c, c["domaine"], c["sous_domaine"]
        return
    contenu = version.contenu if version else contenu_commun_classe(adoption)
    domaines = {d["id"]: d["nom"] for d in contenu.get("domaines", [])}
    sous_domaines = {d["id"]: d["nom"] for d in contenu.get("sous_domaines", [])}
    exclus = set()
    if version:
        reprises = catalogue_reprises(utilisateur=utilisateur, ecole=classe.ecole,
            annee=classe.annee_scolaire, classe=classe).values_list("competence_id", flat=True)
        exclus = set(CompetenceLocale.objects.filter(ecole=classe.ecole).exclude(
            competence_id__in=reprises).values_list("competence_id", flat=True))
    for c in contenu.get("competences", []):
        if c["active"] and c["id"] not in exclus and c["domaine_id"] in domaines:
            yield str(c["id"]), {**c, "domaine_affiche_id": c["domaine_id"],
                                 "sous_domaine_affiche_id": c.get("sous_domaine_id")}, domaines[c["domaine_id"]], sous_domaines.get(c["sous_domaine_id"], "")


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
        contenu = contenu_commun_classe(autre)
        ligne = next(c for c in contenu["competences"] if c["id"] == candidate["id"])
    revision = AdaptationCompetence.objects.filter(classe=classe, competence_id=ligne["id"]
        ).values_list("revision", flat=True).first() or 0
    if revision_attendue is not None and revision != revision_attendue:
        raise ValidationError("Le suivi a changé. Rechargez le formulaire de sélection.")
    locale = CompetenceLocale.objects.filter(ecole=classe.ecole, competence_id=ligne["id"]).first()
    if locale and catalogue_reprises(utilisateur=utilisateur, ecole=classe.ecole,
            annee=classe.annee_scolaire, classe=classe).filter(pk=locale.pk).exists():
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
