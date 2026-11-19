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
    return retour_competences(request, classe) or destination


def retour_competences(request, classe, parametre="retour"):
    try:
        retour = urlsplit(request.GET.get(parametre, "")[:2000])
    except ValueError:
        return ""
    destinations = {reverse(route, args=[classe.pk]) for route in ("catalogue_competences", "choisir_competence")}
    return retour.geturl() if not (retour.scheme or retour.netloc) and retour.path in destinations else ""


def ancrer_competence(retour, identifiant):
    return urlsplit(retour)._replace(fragment=f"c{identifiant}").geturl()


def chemin_classe(classe):
    toutes = classe.statut_annee == "passee" or classe_historique(classe)
    accueil = lien("accueil", **({"toutes": 1} if toutes else {}))
    return [("Les classes", accueil), (classe.libelle_avec_annee, lien("classe_detail", classe.pk))]


def chemin_reglages_referentiel(classe, *, catalogue, inclure_reglages=True):
    chemin = chemin_classe(classe)
    if catalogue:
        chemin.append(("Compétences", lien("catalogue_competences", classe.pk)))
    if inclure_reglages:
        chemin.append(("Réglages du référentiel", lien("referentiel_classe", classe.pk)))
    return chemin


def chemin_retour_competences(classe, retour):
    libelle = ("Saisir pour toute la classe" if urlsplit(retour).path == reverse("choisir_competence", args=[classe.pk])
              else "Compétences")
    return chemin_classe(classe) + [(libelle, retour)]


def chemin_collectif(classe, filtre, competence=None):
    ancre = f"c{competence.pk}" if competence else ""
    return chemin_classe(classe) + [
        ("Saisir pour toute la classe", lien("choisir_competence", classe.pk, filtre=filtre, ancre=ancre)),
    ]


def chemin_competence(classe, competence, filtre, *, ancre=""):
    return chemin_collectif(classe, filtre, competence) + [
        (competence.libelle, lien("saisie_competence", classe.pk, competence.pk, filtre=filtre, ancre=ancre)),
    ]
