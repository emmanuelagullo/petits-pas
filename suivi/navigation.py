"""Destinations de navigation du suivi, reconstruites à partir de routes nommées."""
from urllib.parse import urlencode, urlsplit

from django.urls import reverse

from .referentiels import classe_historique


def filtre_competences(request):
    valeur = request.GET.get("niveaux")
    return valeur if valeur in {"PS", "MS", "GS"} else "tous"


def lien(route, *args, filtre="tous", ancre="", **params):
    if filtre != "tous":
        params["niveaux"] = filtre
    url = reverse(route, args=args)
    if params:
        url += "?" + urlencode(params)
    return url + ("#" + ancre if ancre else "")


def retour_catalogue_ajout(request, classe):
    if request.GET.get("origine") != "catalogue":
        return ""
    destination = reverse("catalogue_competences", args=[classe.pk])
    try:
        retour = urlsplit(request.GET.get("retour", "")[:2000])
    except ValueError:
        retour = None
    if retour and not (retour.scheme or retour.netloc) and retour.path == destination:
        return retour.geturl()
    return destination


def chemin_classe(classe):
    toutes = classe.statut_annee == "passee" or classe_historique(classe)
    accueil = lien("accueil", **({"toutes": 1} if toutes else {}))
    return [("Les classes", accueil), (classe.libelle_avec_annee, lien("classe_detail", classe.pk))]


def chemin_collectif(classe, filtre, competence=None):
    ancre = f"c{competence.pk}" if competence else ""
    return chemin_classe(classe) + [
        ("Saisir pour toute la classe", lien("choisir_competence", classe.pk, filtre=filtre, ancre=ancre)),
    ]


def chemin_competence(classe, competence, filtre, *, ancre=""):
    return chemin_collectif(classe, filtre, competence) + [
        (competence.libelle, lien("saisie_competence", classe.pk, competence.pk, filtre=filtre, ancre=ancre)),
    ]
