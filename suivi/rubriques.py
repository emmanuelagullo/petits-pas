"""Composition des rubriques de classe et visibilité pour la saisie."""
from .models import RubriqueClasse


def personnaliser_rubriques(contenu, classe):
    domaines = {d["id"]: d for d in contenu.setdefault("domaines", [])}
    groupes = {s["id"]: s for s in contenu.setdefault("sous_domaines", [])}
    choix = list(RubriqueClasse.objects.filter(classe=classe).select_related("domaine", "sous_domaine"))
    for regle in choix:
        if regle.sous_domaine_id is None and (regle.creee or regle.domaine_id in domaines):
            ligne = domaines.setdefault(regle.domaine_id, {"id": regle.domaine_id, "code": regle.domaine.code})
            ligne.update(nom=regle.nom, ordre=regle.ordre)
    for regle in choix:
        if regle.sous_domaine_id and regle.domaine_id in domaines and (regle.creee or regle.sous_domaine_id in groupes):
            ligne = groupes.setdefault(regle.sous_domaine_id, {
                "id": regle.sous_domaine_id, "code": regle.sous_domaine.code, "domaine_id": regle.domaine_id,
            })
            ligne.update(nom=regle.nom, ordre=regle.ordre)
    contenu["domaines"] = sorted(domaines.values(), key=lambda d: (d["ordre"], d["id"]))
    contenu["sous_domaines"] = sorted(groupes.values(), key=lambda s: (s["ordre"], s["id"]))
    return contenu


def rubriques_masquees(classe):
    if classe is None:
        return set(), set()
    from .referentiels import classe_historique
    if classe_historique(classe):
        return set(), set()
    domaines, groupes = set(), set()
    for domaine, groupe in RubriqueClasse.objects.filter(classe=classe, masquee=True).values_list("domaine_id", "sous_domaine_id"):
        if groupe is None:
            domaines.add(domaine)
        else:
            groupes.add(groupe)
    return domaines, groupes


def contenu_classement(adoption):
    from .referentiels import contenu_adoption
    contenu = contenu_adoption(adoption)
    domaines, groupes = rubriques_masquees(adoption.classe)
    return {
        "domaines": [d for d in contenu["domaines"] if d["id"] not in domaines],
        "sous_domaines": [s for s in contenu["sous_domaines"] if s["id"] not in groupes and s["domaine_id"] not in domaines],
    }


def rubriques_saisissables(arbre, classe):
    domaines, groupes = rubriques_masquees(classe)
    for domaine in arbre:
        if domaine.pk not in domaines:
            domaine.visibles = [c for c in domaine.visibles if c.sous_domaine_id not in groupes]
            if hasattr(domaine, "sous_domaines_lus"):
                domaine.sous_domaines_lus = [s for s in domaine.sous_domaines_lus if s.pk not in groupes]
            yield domaine
