"""Composition de définitions publiques, sans données de suivi."""
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence

from .apercu_mises_a_jour import comparer_definition
from .paquets_referentiels import empaqueter


def catalogue_composition(versions):
    return {
        f"{version.pk}:{reference_competence(competence)}": (version, competence)
        for version in versions
        for competence in competences_document(version.contenu)
    }


def composer_paquet(catalogue, donnees, references, creations=()):
    groupes = {}
    reprises = {}

    def ajouter(rubrique, competence):
        groupes.setdefault(rubrique, []).append(competence)
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
            ecarts = comparer_definition({c: precedente[c] for c in champs}, {c: competence[c] for c in champs})
            if ecarts:
                resume = ", ".join(f"{d['champ']} ({d['avant']} → {d['apres']})" for d in ecarts)
                raise ValidationError(f"Deux définitions de « {competence['libelle']} » diffèrent : {resume}. "
                                      "Gardez cochée l’édition dont vous souhaitez reprendre la définition.")
            continue
        reprises[cle] = competence
        ajouter(donnees.get("rubrique"), {**competence, "source_origine": origine})

    if donnees.get("nouvelle"):
        ajouter(donnees.get("rubrique"), {"identite": donnees.get("identite_nouvelle"),
                "libelle": donnees["nouvelle"], "niveau": donnees.get("niveau_nouvelle")})
    for creation in creations:
        if creation["libelle"]:
            ajouter(creation["rubrique"] or donnees.get("rubrique"), {
                cle: creation[cle] for cle in ("identite", "libelle", "niveau")
            })
    domaines = []
    rang_competence = 0
    for rang, (rubrique, competences) in enumerate(groupes.items(), start=1):
        for competence in competences:
            rang_competence += 1
            competence["code"] = f"C{rang_competence}"
        domaines.append({"code": f"R{rang}", "nom": rubrique, "competences": competences})
    source = {cle: donnees.get(cle) for cle in ("identifiant", "titre", "provenance", "licence")}
    return empaqueter({
        "format": 2, "source": {**source, "provisoire": True},
        "version": donnees.get("version"),
        "domaines": domaines,
    })
