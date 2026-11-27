"""Projection portable des apprentissages communs d’une classe."""
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db.models import Q

from suivi.identites_referentiels import competences_document, identifiant_diffusion, reference_competence, references_suivi
from suivi.models import AdaptationCompetence, CompetenceLocale, CompetenceSourceEcole, InformationsPartageReferentielClasse, SourceReferentiel
from suivi.presentation import illustration_effective, propositions, reglages_du_perimetre
from suivi.referentiels import adoption_courante, arbre_version, contenu_adoption
from suivi.rubriques import rubriques_saisissables
from .licences_diffusion import droits_competence, encoder_droits, licence_renseignee, resoudre_licence


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


def code_competence_partagee(classe, competence_id):
    return "C" + sha256(f"{classe.ecole_id}/{competence_id}".encode()).hexdigest()[:19]


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

    reglages = reglages_du_perimetre(classe.ecole, classe)
    base = adoption.version
    droits_base = {}
    if base.contenu.get("origine") == "source_declaree":
        references = references_suivi(classe.ecole, base)
        droits_base = {references[reference_competence(c)]: droits_competence(base.contenu, c)
                       for c in competences_document(base.contenu) if reference_competence(c) in references}
    source = dict(source)
    licence_creations = source.pop("licence_creations", "") or licence_creations_classe(adoption)
    notices = {}
    locales = dict(CompetenceLocale.objects.filter(
        ecole=classe.ecole, competence_id__in=identites_locales,
    ).values_list("competence_id", "licence_partage"))
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
                "code": code_competence_partagee(classe, competence.pk),
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
            image = illustration_effective(classe.ecole, competence, classe, reglages=reglages)
            if image.icone_png:
                definition["icone_png"] = image.icone_png
            elif image.icone:
                definition["icone"] = image.icone
            notice = (licence_renseignee(base.source.licence), base.source.provenance)
            if origine:
                notice = (licence_renseignee(origine.source.licence), origine.source.provenance)
            if competence.pk in droits_base:
                notice = droits_base[competence.pk]
            if ajout and not ajout.get("variante_de") and not origine:
                licence, _ = resoudre_licence(locales.get(competence.pk), creation=True, defaut_creation=licence_creations)
                notice = (licence, source.get("provenance") or base.source.provenance)
            if ajout.get("variante_de") and not origine:
                notice = (locales.get(competence.pk) or "", ajout["variante_de"]["libelle"])
            notices[definition["code"]] = notice
            groupes[competence.sous_domaine_id].append(definition)
        domaines.append({
            "code": domaine.code, "nom": domaine.nom, "competences": groupes[None],
            "sous_domaines": sous_domaines,
            "attendus": [{"code": a.code, "texte": a.texte} for a in domaine.attendus.all()],
        })
    document = {"format": 2, "version": version, "source": {**source, "provisoire": True},
            "domaines": domaines, "structure_seule": not any(
                d["competences"] or any(s["competences"] for s in d["sous_domaines"]) for d in domaines)}

    document["source"].setdefault("licence", "")
    document["source"].setdefault("provenance", base.source.provenance)
    encoder_droits(document, notices)
    return document



def licence_creations_classe(adoption):
    from .licences_diffusion import licence_creation_effective

    return licence_creation_effective(adoption.classe.ecole, adoption.classe, adoption)


def compter_creations_sans_licence(classe, document):
    codes = {c["code"] for c in competences_document(document) if not c.get("source_origine")}
    if not codes:
        return 0
    locales = CompetenceLocale.objects.filter(ecole=classe.ecole, suivi_libre=False, licence_partage="").exclude(
        definition__has_key="variante_de",
    ).values_list("competence_id", flat=True)
    return sum(code_competence_partagee(classe, pk) in codes for pk in locales)


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


def resoudre_licences_classe(adoption, document):
    sources = sources_referentiel_partage(adoption, document)
    inconnues = [c for c in competences_document(document) if resoudre_licence(droits_competence(document, c)[0])[1]]
    if inconnues:
        choix = InformationsPartageReferentielClasse.objects.filter(
            classe=adoption.classe, adoption=adoption, licences_sources=sorted({licence for _, licence in sources}),
        ).first()
        licence = licence_renseignee(choix.donnees.get("licence", "")) if choix else ""
        portee = choix.donnees.get("competences_licence_confirmee") if choix else None
        if portee is None:
            # Les anciennes confirmations ne couvraient qu'une source.
            portee = [reference_competence(c) for c in inconnues
                      if len(sources) == 1 and not c.get("variante_de")]
        if licence and set(map(reference_competence, inconnues)) <= set(portee):
            encoder_droits(document, {c["code"]: (licence if c in inconnues else droits_competence(document, c)[0],
                                                   droits_competence(document, c)[1])
                                      for c in competences_document(document)})
    notices = {c["code"]: droits_competence(document, c) for c in competences_document(document)}
    encoder_droits(document, {code: (resoudre_licence(licence)[0], credits)
                              for code, (licence, credits) in notices.items()})
    return resoudre_licence(document["source"]["licence"])[0]
