from django import template

from suivi.autorisations import VOIR_CLASSE, VOIR_SUIVI, autorise
from suivi.navigation import chemin_classe, chemin_collectif, chemin_reglages_referentiel, filtre_competences, lien

register = template.Library()


@register.inclusion_tag("suivi/partiels/ariane.html", takes_context=True)
def ariane_classe(context, page, classe, collectif=False):
    filtre = filtre_competences(context["request"])
    chemin = chemin_collectif(classe, filtre) if collectif else chemin_classe(classe)
    if not collectif and page == classe.libelle_avec_annee:
        chemin = chemin[:-1]
    return {"ariane": chemin, "page": page}


@register.inclusion_tag("suivi/partiels/ariane.html", takes_context=True)
def ariane_eleve(context, page, eleve, parent=False):
    request = context["request"]
    classe = context.get("classe") or eleve.classe
    chemin = chemin_classe(classe) if classe and autorise(request.user, VOIR_CLASSE, classe) else []
    if parent and not eleve.archive_le and autorise(request.user, VOIR_SUIVI, eleve):
        chemin.append((eleve.nom_court, lien("saisie_eleve", eleve.pk, filtre=filtre_competences(request))))
    return {"ariane": chemin, "page": page}


@register.inclusion_tag("suivi/partiels/ariane.html", takes_context=True)
def ariane_referentiel(context, page, classe, annee):
    if classe:
        chemin = chemin_reglages_referentiel(classe, catalogue=autorise(context["request"].user, VOIR_SUIVI, classe))
    else:
        chemin = [("Gérer l’école", lien("gestion")),
                  ("Référentiels de l’école", lien("referentiels_ecole", annee=annee))]
    return {"ariane": chemin, "page": page}


@register.inclusion_tag("suivi/partiels/ariane.html")
def ariane_gestion(page):
    return {"ariane": [("Gérer l’école", lien("gestion"))], "page": page}


@register.simple_tag
def lien_ajout_competence(classe, filtre="tous", domaine=None, sous_domaine=None, eleve=None, collectif=False):
    """Entrée commune, avec le contexte de la saisie conservé dans le GET."""
    parametres = {"ajouter": 1}
    if filtre != "tous":
        parametres["niveau"] = filtre
    if domaine:
        parametres["classement"] = getattr(domaine, "parents_sous_domaines", {}).get(sous_domaine, domaine.pk)
    if sous_domaine:
        parametres["groupe"] = sous_domaine
    if eleve:
        parametres["eleve"] = eleve.pk
    if collectif:
        parametres["collectif"] = 1
    return lien("choisir_competence" if collectif else "catalogue_competences", classe.pk, **parametres)
