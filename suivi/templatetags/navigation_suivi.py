from django import template

from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, VOIR_CLASSE, VOIR_SUIVI, autorise
from suivi.contexte_ecole import ecole_courante
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
def ariane_referentiel(context, page, classe, annee, parcours="reglages"):
    request = context["request"]
    if context.get("retour_export_ecole"):
        chemin = [("Gérer l’école", lien("gestion")),
                  ("Référentiels de l’école", lien("referentiels_ecole", annee=annee)),
                  ("Exporter depuis l’école", context["retour_export_ecole"])]
    elif classe:
        chemin = chemin_reglages_referentiel(
            classe, catalogue=autorise(request.user, VOIR_SUIVI, classe),
            inclure_reglages=parcours == "reglages" and autorise(request.user, GERER_REFERENTIEL_CLASSE, classe),
        )
        if context.get("retour_reglages"):
            chemin.append(("Réglages du référentiel", context["retour_reglages"]))
        if parcours in ("partage", "equipe") or context.get("retour_catalogues") or context.get("retour_espace"):
            retour = context.get("retour_catalogues") or context.get("retour_espace")
            if parcours == "equipe":
                retour = lien("suivis_referentiels_classe", classe.pk, espace=1, ancre="espace-partage")
            chemin.append(("Catalogues et partage", retour or lien("suivis_referentiels_classe", classe.pk)))
        elif context.get("retour_competences") and chemin[-1][0] == "Compétences":
            chemin[-1] = ("Compétences", context["retour_competences"])
        if context.get("retour_import"):
            chemin.append(("Importer une édition", context["retour_import"]))
    else:
        chemin = []
        if autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole_courante(request)):
            parametres = {"annee": annee} if annee else {}
            chemin.extend([("Gérer l’école", lien("gestion")),
                           ("Référentiels de l’école", lien("referentiels_ecole", **parametres))])
        if context.get("retour_propositions"):
            chemin.append(("Propositions reçues", context["retour_propositions"]))
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


@register.inclusion_tag("suivi/partiels/echange_contenu_hote.html", takes_context=True)
def contenu_echange_hote(context, echange):
    return {**context.flatten(), **echange, "request": echange["requete_echange"]}


@register.inclusion_tag("suivi/partiels/reponse_examen_catalogue.html", takes_context=True)
def examen_catalogue_hote(context, echange):
    return {**context.flatten(), **echange, "request": echange["requete_echange"]}
