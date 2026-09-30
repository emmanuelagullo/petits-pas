"""Lecture du référentiel commune aux saisies, réglages et carnets."""
from django.db.models import Prefetch

from .models import AdoptionReferentiel, Attendu, Competence, Domaine, SousDomaine


def adoption_courante(classe):
    if classe is None:
        return None
    if not hasattr(classe, "_adoption_referentiel_lecture"):
        classe._adoption_referentiel_lecture = AdoptionReferentiel.objects.filter(
            classe=classe, courante=True).select_related("version", "annuel").first()
    return classe._adoption_referentiel_lecture


def arbre_version(ecole, contenu, *, niveaux=None, inclure_ids=(), masquer=True, masque_actuel=True):
    """Objets de lecture : aucune réécriture du catalogue ou de ses relations."""
    domaines = {}
    for ligne in contenu.get("domaines", []):
        domaine = Domaine(ecole=ecole, **ligne)
        domaine.visibles = []
        domaine._prefetched_objects_cache = {"attendus": []}
        domaines[domaine.pk] = domaine
    sous_domaines = {s["id"]: SousDomaine(**s) for s in contenu.get("sous_domaines", [])}
    for ligne in contenu.get("attendus", []):
        domaine = domaines.get(ligne["domaine_id"])
        if domaine:
            domaine._prefetched_objects_cache["attendus"].append(Attendu(**ligne))
    ids = [c["id"] for c in contenu.get("competences", [])]
    actuelles = Competence.objects.in_bulk(ids)
    for ligne in contenu.get("competences", []):
        actuelle = actuelles.get(ligne["id"])
        if actuelle is None:
            continue
        if niveaux and ligne["niveau"] not in niveaux:
            continue
        if masquer and (not ligne["active"] or (masque_actuel and not actuelle.active)) and ligne["id"] not in inclure_ids:
            continue
        competence = Competence(**ligne)
        competence.domaine = domaines[ligne["domaine_id"]]
        competence.sous_domaine = sous_domaines.get(ligne["sous_domaine_id"])
        domaines[ligne["domaine_id"]].visibles.append(competence)
    for domaine in domaines.values():
        domaine.visibles.sort(key=lambda c: (c.ordre, c.pk))
    return sorted(domaines.values(), key=lambda d: (d.ordre, d.pk))


def arbre_competences(ecole, niveaux=None, *, classe=None, inclure_ids=()):
    if classe is not None and classe.ecole_id != ecole.pk:
        raise ValueError("Classe d'une autre école.")
    adoption = adoption_courante(classe)
    if adoption:
        contenu = adoption.etat_final.get("contenu", adoption.version.contenu) if adoption.clos else adoption.version.contenu
        return arbre_version(ecole, contenu, niveaux=niveaux, inclure_ids=inclure_ids, masque_actuel=not adoption.clos)

    competences = ((Competence.objects.filter(active=True) | Competence.objects.filter(pk__in=inclure_ids))
                   .select_related("sous_domaine", "domaine__ecole")
                   .order_by("ordre", "pk"))
    if niveaux:
        competences = competences.filter(niveau__in=niveaux)
    return Domaine.objects.filter(ecole=ecole).order_by("ordre", "pk").prefetch_related(
        Prefetch("competences", queryset=competences, to_attr="visibles"),
        "attendus",
    )
