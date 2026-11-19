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


def origine_rubrique(domaine):
    """Libellé historique des regroupements d'ajouts, hors personnalisations."""
    if domaine.code.startswith("ajout-") and domaine.nom.startswith("Ajouts — "):
        return domaine.nom.removeprefix("Ajouts — ")
    return None


def rattachements_rubriques(adoption, domaines, groupes):
    """Pour les ajouts historiques, employer une correspondance non ambiguë de la base."""
    if not adoption or adoption.clos:
        return {}, {}
    from .referentiels import contenu_origine

    origine = contenu_origine(adoption)
    disponibles = {d.pk for d in domaines}
    bases = {}
    for d in origine.get("domaines", []):
        bases.setdefault(d["nom"], []).append(d["id"])
    parents = {}
    for domaine in domaines:
        candidats = bases.get(origine_rubrique(domaine), [])
        if len(candidats) == 1 and candidats[0] in disponibles and candidats[0] != domaine.pk:
            parents[domaine.pk] = candidats[0]
    sous_base = {}
    for s in origine.get("sous_domaines", []):
        sous_base.setdefault((s["domaine_id"], s["nom"]), []).append(s["id"])
    existants = {s.pk for s in groupes}
    enfants = {}
    for sous in groupes:
        candidats = sous_base.get((parents.get(sous.domaine_id), sous.nom), [])
        if len(candidats) == 1 and candidats[0] in existants:
            enfants[sous.pk] = candidats[0]
    return parents, enfants


def regrouper_rubriques_saisie(arbre, adoption):
    """Rattacher les ajouts dans la lecture seule, avant d'appliquer les masquages."""
    domaines = {d.pk: d for d in arbre}
    if not adoption or adoption.clos:
        return list(domaines.values())
    groupes = [s for d in domaines.values() for s in getattr(d, "sous_domaines_lus", [])]
    parents, enfants = rattachements_rubriques(adoption, list(domaines.values()), groupes)
    domaines_masques, groupes_masques = rubriques_masquees(adoption.classe)
    for domaine in list(domaines.values()):
        libelle = origine_rubrique(domaine)
        if libelle is None:
            continue
        parent = domaines.get(parents.get(domaine.pk))
        if parent is None:
            domaine.nom = libelle
            continue
        del domaines[domaine.pk]
        if domaine.pk in domaines_masques or parent.pk in domaines_masques:
            continue
        correspondances = getattr(parent, "rattachements_sous_domaines", {})
        for sous in domaine.sous_domaines_lus:
            if sous.pk in enfants:
                correspondances[sous.pk] = enfants[sous.pk]
            elif sous.pk not in groupes_masques:
                parent.sous_domaines_lus.append(sous)
        parent.rattachements_sous_domaines = correspondances
        parent.parents_sous_domaines = {s.pk: s.domaine_id for s in parent.sous_domaines_lus}
        parent.visibles.extend(c for c in domaine.visibles if c.sous_domaine_id not in groupes_masques
                               and enfants.get(c.sous_domaine_id) not in groupes_masques)
    return list(domaines.values())
