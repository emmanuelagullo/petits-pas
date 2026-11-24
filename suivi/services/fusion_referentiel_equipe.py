"""Fusion de trois documents de diffusion d'un même référentiel d'équipe."""
from dataclasses import dataclass

from suivi.identites_referentiels import reference_competence

_ABSENT = object()
_CLES_LISTES = {
    "domaines": lambda rubrique: rubrique["code"],
    "sous_domaines": lambda rubrique: rubrique["code"],
    "competences": reference_competence,
    "attendus": lambda attendu: attendu["code"],
    "formulations": lambda formulation: formulation["code"],
}


@dataclass(frozen=True)
class ConflitReferentiel:
    chemin: tuple[str, ...]
    base: object
    locale: object
    distante: object


def fusionner_referentiel_equipe(base, locale, distante, *, choix=None):
    """Retourne le document à valider ou les conflits, sans publier de version.

    Les entrées sont des documents de diffusion validés. Le numéro de la
    prochaine édition appartient à l'appelant, après décision sur les conflits.
    """
    conflits = []

    def conflit(chemin, avant, ici, ailleurs):
        choix_champ = (choix or {}).get(chemin)
        if choix_champ in ("locale", "distante") and chemin[-1] != "emplacement":
            return ici if choix_champ == "locale" else ailleurs
        valeurs = [None if valeur is _ABSENT else valeur for valeur in (avant, ici, ailleurs)]
        conflits.append(ConflitReferentiel(chemin, *valeurs))
        return avant

    def fusion(chemin, avant, ici, ailleurs):
        if ici == ailleurs or ailleurs == avant:
            return ici
        if ici == avant:
            return ailleurs
        if all(isinstance(valeur, dict) for valeur in (avant, ici, ailleurs)):
            resultat = {}
            for cle in dict.fromkeys([*avant, *ici, *ailleurs]):
                valeur = fusion((*chemin, cle), avant.get(cle, _ABSENT),
                                ici.get(cle, _ABSENT), ailleurs.get(cle, _ABSENT))
                if valeur is not _ABSENT:
                    resultat[cle] = valeur
            return resultat
        cle_liste = _CLES_LISTES.get(chemin[-1]) if chemin else None
        if cle_liste and all(isinstance(valeur, list) for valeur in (avant, ici, ailleurs)):
            index_base, index_local, index_distant = (
                {cle_liste(entree): entree for entree in liste}
                for liste in (avant, ici, ailleurs)
            )
            entrees = fusion(chemin, index_base, index_local, index_distant)
            # Comparer les réordonnancements sur le périmètre encore commun.
            commun = index_base.keys() & index_local.keys() & index_distant.keys()
            ordres = [[cle for cle in index if cle in commun]
                      for index in (index_base, index_local, index_distant)]
            ordre = fusion((*chemin, "ordre"), *ordres)
            if ordres[1] == ordres[2]:
                premier, second = sorted((index_local, index_distant), key=list)
            elif ordre == ordres[1]:
                premier, second = index_local, index_distant
            else:
                premier, second = index_distant, index_local
            # Garder la position des entrées du premier ordre et insérer les
            # nouvelles entrées de l'autre branche près de leur prédécesseur.
            placement = [cle for cle in premier if cle in entrees]
            precedent = None
            for cle in second:
                if cle not in entrees:
                    continue
                if cle not in placement:
                    placement.insert(placement.index(precedent) + 1 if precedent else 0, cle)
                precedent = cle
            return [entrees[cle] for cle in placement]
        return conflit(chemin, avant, ici, ailleurs)

    documents = [{cle: valeur for cle, valeur in document.items() if cle not in
                  ("version", "structure_seule")} for document in (base, locale, distante)]
    resultat = fusion((), *documents)
    if conflits:
        return None, conflits
    # Deux déplacements vers des rubriques différentes se manifestent par
    # deux ajouts de la même identité et un retrait commun de l'emplacement.
    emplacements = {}
    for domaine in resultat["domaines"]:
        groupes = [(domaine, (domaine["code"],))]
        groupes.extend((sous, (domaine["code"], sous["code"]))
                      for sous in domaine.get("sous_domaines", []))
        for groupe, position in groupes:
            for competence in groupe.get("competences", []):
                reference = reference_competence(competence)
                if reference in emplacements:
                    conflit(("competences", reference, "emplacement"), _ABSENT,
                            emplacements[reference], position)
                emplacements[reference] = position
    if conflits:
        return None, conflits
    return {**resultat, "structure_seule": not emplacements}, []
