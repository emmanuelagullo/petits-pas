"""Préparer une sélection partageable depuis les sources consultables d’une classe."""
from hashlib import sha256

import yaml
from django.core.exceptions import ValidationError
from django.db.models import Q

from suivi.adaptations_referentiels import contenu_adapte
from suivi.ajouts_referentiels import definition_effective_ajout
from suivi.identites_referentiels import identifiant_diffusion, reference_competence
from suivi.models import CompetenceLocale, SourceReferentiel
from suivi.referentiels import contenu_adoption
from suivi.presentation import illustration_effective, propositions, reglages_du_perimetre
from .ajouts_referentiels import catalogue_reprises
from .apercu_mises_a_jour import comparer_definition
from .paquets_referentiels import document_ajout
from .partage_referentiel_classe import code_competence_partagee, preparer_referentiel_classe
from .sources_catalogue import sources_catalogue

MAX_SELECTION = 500
LICENCES_PARTAGEABLES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0"}


def parcourir_document(document):
    for domaine in document["domaines"]:
        for competence in domaine["competences"]:
            yield domaine["nom"], "", competence
        for sous in domaine.get("sous_domaines", []):
            for competence in sous["competences"]:
                yield domaine["nom"], sous["nom"], competence


def document_selection(adoption, cles, *, utilisateur=None):
    classe = adoption.classe
    origine = adoption.version.source
    document = preparer_referentiel_classe(classe, {}, "1")
    codes = {code_competence_partagee(classe, cle): cle for cle in cles if cle.isascii() and cle.isdecimal()}
    locales = dict(CompetenceLocale.objects.filter(
        ecole=classe.ecole, competence_id__in=[cle for cle in codes.values() if len(cle) <= 18],
    ).values_list("competence_id", "licence_partage"))
    retenues = [(rubrique, sous, c) for rubrique, sous, c in parcourir_document(document) if c["code"] in codes]
    origines = {c["source_origine"] for _, _, c in retenues if c.get("source_origine")}
    sources = {identifiant_diffusion(source): source for source in SourceReferentiel.objects.filter(
        Q(ecole=classe.ecole, identifiant_diffusion__in=origines)
        | Q(ecole__isnull=True, identifiant__in=origines)
    ).order_by("pk")}
    sources[identifiant_diffusion(origine)] = origine
    for rubrique, sous, competence in retenues:
        cle = codes[competence["code"]]
        reference = competence.get("source_origine")
        definition = sources.get(reference)
        if definition:
            credit = (definition.titre, definition.licence, definition.provenance)
        elif reference:
            credit = (reference, "", "")
        else:
            credit = (origine.titre, locales.get(int(cle)) or origine.licence, origine.provenance)
        yield cle, rubrique, sous, competence, (credit,)
    if utilisateur is not None:
        # Les ajouts proposés dans « Compétences de la classe » sont accessibles
        # même avant leur inscription dans le référentiel de la classe.
        presents = {code_competence_partagee(classe, c["id"]) for c in contenu_adoption(adoption)["competences"]}
        candidats = [cle for code, cle in codes.items() if code not in presents and len(cle) <= 18]
        if not candidats:
            return
        reglages = reglages_du_perimetre(classe.ecole, classe)
        for locale in catalogue_reprises(utilisateur=utilisateur, ecole=classe.ecole,
                                       annee=classe.annee_scolaire, classe=classe).filter(
            competence_id__in=candidats,
        ).select_related("competence__domaine", "competence__sous_domaine"):
            c = locale.competence
            definition = contenu_adapte(classe.ecole, classe.annee_scolaire,
                                        definition_effective_ajout(locale), classe)["competences"][0]
            illustration = illustration_effective(classe.ecole, c, classe, reglages=reglages)
            licence = locale.licence_partage or ("" if locale.definition.get("variante_de") else "CC-BY-SA-4.0")
            phrases = [{"code": p["cle"], "texte": p["texte"]} for p in propositions(c, classe)]
            contenu = document_ajout(locale, definition, provenance="Ajout local", licence=licence,
                                     icone=illustration.icone or "", formulations=phrases)
            competence = contenu["domaines"][0]["competences"][0]
            if illustration.icone_png:
                competence["icone_png"] = illustration.icone_png
            yield str(c.pk), c.domaine.nom, c.sous_domaine.nom if c.sous_domaine else "", competence, (
                (c.libelle, licence, "Ajout local"),)



def preparer_selection(utilisateur, adoption, cles, choix):
    cles = sorted(set(cles))
    if not 0 < len(cles) <= MAX_SELECTION or any(len(cle) > 280 for cle in cles):
        raise ValidationError(f"Sélectionnez entre 1 et {MAX_SELECTION} compétences.")
    classe = adoption.classe
    sources = sources_catalogue(utilisateur, classe, adoption)
    demandes = {}
    for cle in cles:
        source, _, reference = cle.partition(":")
        demandes.setdefault(source, {})[reference] = cle

    identites, trouvees = {}, set()
    for source, references in demandes.items():
        if source == "classe":
            titre = classe.nom
            lignes = document_selection(adoption, references, utilisateur=utilisateur)
        else:
            catalogue = sources.get(source)
            if catalogue is None:
                continue
            titre, version, autre = catalogue
            if autre and not autre.clos:
                lignes = document_selection(autre, references)
            elif version and version.contenu.get("origine") == "source_declaree":
                diffusion = version.contenu["source"]
                lignes = ((reference_competence(c), rubrique, sous,
                           {**c, "source_origine": c.get("source_origine", diffusion["identifiant"])},
                           ((diffusion["titre"], diffusion["licence"], diffusion["provenance"]),))
                          for rubrique, sous, c in parcourir_document(version.contenu))
            else:
                continue
        for reference, rubrique, sous, competence, credits in lignes:
            if reference not in references:
                continue
            cle = references[reference]
            trouvees.add(cle)
            identite = reference_competence(competence)
            identites.setdefault(identite, []).append({
                "cle": cle, "titre": titre, "source": source, "rubrique": rubrique, "sous": sous,
                "competence": competence, "credits": credits,
            })
    if trouvees != set(cles):
        raise ValidationError("Certaines compétences cochées ne sont plus partageables. Revenez à la liste pour modifier la sélection.")

    conflits, retenues = [], []
    champs = ("libelle", "niveau", "icone", "icone_png", "formulations")

    def definition(variante):
        return {champ: variante["competence"].get(champ) for champ in champs}

    for variantes in identites.values():
        locale = next((v for v in variantes if v["source"] == "classe"), None)
        retenue = locale or next((v for v in variantes if v["cle"] in choix), variantes[0])
        if not locale and retenue["cle"] not in choix:
            for variante in variantes:
                variante["ecarts"] = comparer_definition(definition(retenue), definition(variante))
            if any(v["ecarts"] for v in variantes):
                conflits.append(variantes)
        retenues.append(retenue)

    catalogues = sorted({v["source"]: v["titre"] for v in retenues}.values())
    credits = sorted({credit for v in retenues for credit in v["credits"]})
    licences = {licence for _, licence, _ in credits}
    licence = next(iter(licences)) if len(licences) == 1 else ""
    titre = f"Sélection de compétences – {catalogues[0]}" if len(catalogues) == 1 else f"Sélection de compétences – {len(catalogues)} sources"
    groupes = {}
    for indice, v in enumerate(retenues, 1):
        sous = groupes.setdefault((v["source"], v["rubrique"]), {})
        sous.setdefault(v["sous"], []).append({**v["competence"], "code": f"C{indice}"})
    domaines = []
    for indice, ((_, rubrique), sous) in enumerate(groupes.items(), 1):
        domaines.append({"code": f"R{indice}", "nom": rubrique, "competences": sous.pop("", []),
                         "sous_domaines": [{"code": f"S{i}", "nom": nom, "competences": competences}
                                          for i, (nom, competences) in enumerate(sous.items(), 1)]})
    empreinte = sha256(yaml.safe_dump(domaines, allow_unicode=True).encode()).hexdigest()
    provenance = "; ".join(f"{nom} ({licence_source or 'licence à vérifier'}). {attribution}"
                           for nom, licence_source, attribution in credits)
    if len(provenance) > 4000:
        raise ValidationError("Les crédits dépassent la place disponible dans un ZIP. Réduisez le nombre de sources.")
    document = {"format": 2, "version": "1", "domaines": domaines, "source": {
        "identifiant": f"selection-{empreinte}", "titre": titre[:200], "provisoire": True,
        "provenance": provenance,
        "licence": licence or "À vérifier",
    }}
    return document, catalogues, [(nom, l) for nom, l, _ in credits], conflits, licence in LICENCES_PARTAGEABLES
