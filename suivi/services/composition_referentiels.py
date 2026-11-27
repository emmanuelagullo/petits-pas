"""Composition de définitions publiques, sans données de suivi."""
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence

from .apercu_mises_a_jour import comparer_definition
from .paquets_referentiels import empaqueter
from .licences_diffusion import droits_competence, encoder_droits, resoudre_licence


def catalogue_composition(versions):
    return {
        f"{version.pk}:{reference_competence(competence)}": (version, competence)
        for version in versions
        for competence in competences_document(version.contenu)
    }


def composer_paquet(catalogue, donnees, references, creations=()):
    groupes = {}
    reprises = {}
    source = {cle: donnees.get(cle) for cle in ("identifiant", "titre", "provenance", "licence")}
    source["licence"] = resoudre_licence(source["licence"], creation=True)[0]

    def ajouter(rubrique, competence, notice=None):
        groupes.setdefault(rubrique, []).append((competence, notice or (source["licence"], source["provenance"])))
    for reference in dict.fromkeys(references):
        if reference not in catalogue:
            raise ValidationError("Une compétence sélectionnée n’est plus disponible.")
        version, competence = catalogue[reference]
        origine = competence.get("source_origine", version.contenu["source"]["identifiant"])
        if origine == donnees.get("identifiant"):
            raise ValidationError("Choisissez un identifiant différent des sources reprises.")
        cle = (origine, competence["identite"])
        precedente = reprises.get(cle)
        if precedente:
            champs = ("libelle", "niveau", "icone", "formulations")
            ecarts = comparer_definition(
                {c: precedente.get(c) for c in (*champs, "icone_png")},
                {c: competence.get(c) for c in (*champs, "icone_png")})
            if ecarts:
                resume = ", ".join(f"{d['champ']} ({d['avant']} → {d['apres']})" for d in ecarts)
                raise ValidationError(f"Deux définitions de « {competence['libelle']} » diffèrent : {resume}. "
                                      "Gardez cochée l’édition dont vous souhaitez reprendre la définition.")
            continue
        reprises[cle] = competence
        licence, credits = droits_competence(version.contenu, competence)
        ajouter(donnees.get("rubrique"), {**competence, "source_origine": origine},
                (resoudre_licence(licence)[0], credits))

    if donnees.get("nouvelle"):
        ajouter(donnees.get("rubrique"), {"identite": donnees.get("identite_nouvelle"),
                "libelle": donnees["nouvelle"], "niveau": donnees.get("niveau_nouvelle")})
    for creation in creations:
        if creation["libelle"]:
            ajouter(creation["rubrique"] or donnees.get("rubrique"), {
                cle: creation[cle] for cle in ("identite", "libelle", "niveau")
            })
    domaines, notices = [], {}
    for rang, (rubrique, entrees) in enumerate(groupes.items(), 1):
        competences = []
        for competence, notice in entrees:
            code = f"C{len(notices) + 1}"
            competence["code"] = code
            notices[code] = notice
            competences.append(competence)
        domaines.append({"code": f"R{rang}", "nom": rubrique, "competences": competences})
    document = {
        "format": 2, "source": {**source, "provisoire": True},
        "version": donnees.get("version"),
        "domaines": domaines,
    }
    encoder_droits(document, notices, conserver_defaut=True)
    return empaqueter(document)
