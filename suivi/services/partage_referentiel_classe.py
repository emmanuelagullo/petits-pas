"""Projection portable des apprentissages communs d’une classe."""
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db.models import Q

from suivi.identites_referentiels import competences_document, identifiant_diffusion
from suivi.models import AdaptationCompetence, CompetenceLocale, CompetenceSourceEcole, SourceReferentiel
from suivi.presentation import illustration_effective, propositions
from suivi.referentiels import adoption_courante, arbre_version, contenu_adoption
from suivi.rubriques import rubriques_saisissables


def arbre_commun_classe(adoption, contenu):
    """Arbre pédagogique partagé par la consultation de classe et les exports."""
    classe = adoption.classe
    exclus = set(CompetenceLocale.objects.filter(ecole=classe.ecole, suivi_libre=True)
                 .values_list("competence_id", flat=True))
    exclus.update(AdaptationCompetence.objects.filter(
        classe=classe, annee_scolaire=classe.annee_scolaire, selection_eleves=True,
    ).values_list("competence_id", flat=True))
    for domaine in rubriques_saisissables(arbre_version(classe.ecole, contenu, masque_actuel=False), classe):
        domaine.visibles = [c for c in domaine.visibles if c.pk not in exclus]
        yield domaine


def contenu_commun_classe(adoption, *, avec_heritage=True):
    brut = contenu_adoption(adoption, avec_heritage=avec_heritage)
    contenu = {**brut, "domaines": [], "sous_domaines": [], "competences": []}
    definitions = {c["id"]: c for c in brut["competences"]}
    domaines = {d["id"]: d for d in brut["domaines"]}
    groupes = {g["id"]: g for g in brut.get("sous_domaines", [])}
    for domaine in arbre_commun_classe(adoption, brut):
        contenu["domaines"].append(domaines[domaine.pk])
        contenu["sous_domaines"].extend(groupes[g.pk] for g in domaine.sous_domaines_lus)
        for groupe in [None, *domaine.sous_domaines_lus]:
            cle = groupe.pk if groupe else None
            contenu["competences"].extend(definitions[c.pk] for c in domaine.visibles
                                          if c.sous_domaine_id == cle)
    return contenu


def preparer_referentiel_classe(classe, source, version):
    adoption = adoption_courante(classe)
    if adoption is None:
        raise ValidationError("Choisissez d’abord une base pour cette classe.")
    contenu = contenu_adoption(adoption)
    origines = {
        liaison.competence_id: liaison.identite
        for liaison in CompetenceSourceEcole.objects.filter(
            ecole=classe.ecole, competence_id__in=[c["id"] for c in contenu["competences"]],
        ).select_related("identite__source")
    }

    identites_locales = {
        pk: definition
        for pk, definition in CompetenceLocale.objects.filter(
            ecole=classe.ecole, competence_id__in=[c["id"] for c in contenu["competences"]]
        ).values_list("competence_id", "definition")
    }

    domaines = []
    for domaine in arbre_commun_classe(adoption, contenu):
        groupes = {None: []}
        sous_domaines = []
        for sous in domaine.sous_domaines_lus:
            groupes[sous.pk] = []
            sous_domaines.append({"code": sous.code, "nom": sous.nom, "competences": groupes[sous.pk]})
        for competence in domaine.visibles:
            origine = origines.get(competence.pk)
            cle = sha256(f"{classe.ecole_id}/{competence.pk}".encode()).hexdigest()
            ajout = identites_locales.get(competence.pk, {})
            definition = {
                "identite": origine.identifiant if origine else (ajout.get("identite_portable") or f"classe-{cle}"),
                "code": f"C{cle[:19]}",
                "libelle": competence.libelle, "niveau": competence.niveau,
                "formulations": [{"code": entree["cle"], "texte": entree["texte"]}
                                 for entree in propositions(competence, classe)],
            }
            if origine:
                definition["source_origine"] = identifiant_diffusion(origine.source)
                if definition["source_origine"] == source.get("identifiant"):
                    raise ValidationError("Donnez à ce référentiel un identifiant différent de la base d’origine.")
            if ajout.get("variante_de"):
                definition["variante_de"] = ajout["variante_de"]
            image = illustration_effective(classe.ecole, competence, classe)
            if image.icone_png:
                definition["icone_png"] = image.icone_png
            elif image.icone:
                definition["icone"] = image.icone
            groupes[competence.sous_domaine_id].append(definition)
        domaines.append({
            "code": domaine.code, "nom": domaine.nom, "competences": groupes[None],
            "sous_domaines": sous_domaines,
            "attendus": [{"code": a.code, "texte": a.texte} for a in domaine.attendus.all()],
        })
    return {"format": 2, "version": version, "source": {**source, "provisoire": True},
            "domaines": domaines, "structure_seule": not any(
                d["competences"] or any(s["competences"] for s in d["sous_domaines"]) for d in domaines)}



def sources_referentiel_partage(adoption, document):
    origines = {c["source_origine"] for c in competences_document(document) if c.get("source_origine")}
    sources = SourceReferentiel.objects.filter(
        Q(ecole=adoption.classe.ecole, identifiant_diffusion__in=origines) |
        Q(ecole__isnull=True, identifiant__in=origines)
    )
    base = adoption.version.source
    par_reference = {identifiant_diffusion(source): (source.titre, source.licence.strip())
                     for source in sources.order_by("pk")}
    for source in sources.filter(ecole=adoption.classe.ecole):
        par_reference[identifiant_diffusion(source)] = (source.titre, source.licence.strip())
    par_reference[identifiant_diffusion(base)] = (base.titre, base.licence.strip())
    return [par_reference.get(reference, (reference, "")) for reference in
            sorted(origines | {identifiant_diffusion(base)})]


def licences_referentiel_partage(adoption, document):
    return sorted({licence for _, licence in sources_referentiel_partage(adoption, document)})


def verifier_licence_synchronisation(adoption, document):
    from suivi.models import InformationsPartageReferentielClasse

    sources = sources_referentiel_partage(adoption, document)
    inconnues = [titre for titre, licence in sources if licence.casefold() in
                 {"", "non renseignée", "non renseigné", "inconnue"}]
    if inconnues:
        if len(sources) == 1:
            choix = InformationsPartageReferentielClasse.objects.filter(
                classe=adoption.classe, adoption=adoption, licences_sources=[sources[0][1]],
            ).first()
            if choix:
                licence = choix.donnees.get("licence", "").strip()
                if licence.casefold() not in {"", "non renseignée", "non renseigné", "inconnue"}:
                    return licence
        raise ValidationError("Licence à vérifier pour %(sources)s.",
                              params={"sources": ", ".join(inconnues)})
    if len({licence for _, licence in sources}) != 1:
        raise ValidationError("Vérifiez les licences des sources : %(sources)s.",
                              params={"sources": ", ".join(f"{titre} ({licence})" for titre, licence in sources)})
    return sources[0][1]
