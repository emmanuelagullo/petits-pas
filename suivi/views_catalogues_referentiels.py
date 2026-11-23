"""Découverte et suivi des référentiels à l’échelle d’une école."""
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_ECOLE, IMPORTER_REFERENTIEL_ECOLE, autorise
from .contexte_ecole import ecole_courante
from .identites_referentiels import identifiant_source_ecole
from .models import Ecole, VersionReferentiel, annee_scolaire_pour
from .navigation import lien
from .services.catalogue_fourni import REFERENTIELS_DEPART
from .services.catalogues_externes import CATALOGUE_DEMONSTRATION, identite_grist, lire_catalogue_grist
from .services.choix_bases_referentiels import verifier_annee
from .views import acces_requis

CATALOGUES_FOURNIS = {
    CATALOGUE_DEMONSTRATION: {
        "url": CATALOGUE_DEMONSTRATION, "nom": "Catalogue de démonstration Petits Pas",
        "referentiels": [{"reference": "demo-cycle1", "titre": "Langage en maternelle", "editions": [2, 1]}],
    },
}


@lru_cache(maxsize=1)
def referentiels_fournis():
    resultat = []
    for cle, titre, chemin in REFERENTIELS_DEPART:
        document = yaml.safe_load((Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8"))
        source = document["source"]
        resultat.append({"reference": cle, "identifiant_local": source["identifiant"], "titre": titre,
                         "editions": [document["version"]], "provenance": source["provenance"],
                         "licence": source["licence"]})
    return resultat


def catalogues_visibles(reglages):
    return {
        "petits-pas": {"nom": "Petits Pas", "referentiels": referentiels_fournis()},
        **CATALOGUES_FOURNIS, **{cle: etat["catalogue"] for cle, etat in reglages.items() if "catalogue" in etat},
    }


def enregistrer_catalogue(ecole, utilisateur, cle, *, catalogue=None, reference=None, suivre=False):
    with transaction.atomic():
        ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
        if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
            raise PermissionDenied
        etat = ecole.catalogues_referentiels.setdefault(cle, {})
        if catalogue is not None:
            etat["catalogue"] = catalogue
        if reference is not None:
            suivis = set(etat.get("suivis", ()))
            if suivre:
                suivis.add(reference)
            else:
                suivis.discard(reference)
            etat["suivis"] = sorted(suivis)
        ecole.save(update_fields=["catalogues_referentiels"])
    return ecole


@acces_requis
@require_http_methods(["GET", "POST"])
def decouvrir_referentiels(request):
    ecole = ecole_courante(request)
    if not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    annee = request.GET.get("annee") or annee_scolaire_pour(timezone.localdate())
    try:
        verifier_annee(annee)
    except ValidationError as erreur:
        raise Http404 from erreur
    q = request.GET.get("q", "").strip()[:200]
    filtre = request.GET.get("filtre", "")
    if filtre not in {"suivis", "mises-a-jour"}:
        filtre = ""
    navigation = {"depuis": "echange"} if request.GET.get("depuis") == "echange" else {}
    retour = lien("decouvrir_referentiels", annee=annee, q=q, filtre=filtre, **navigation)
    contexte = {"annee": annee, "q": q, "filtre": filtre, "retour": retour,
                "depuis_echange": bool(navigation),
                "examen_grist": lien("paquets_referentiels_ecole", annee=annee, origine="decouverte",
                                     q=q, filtre=filtre, **navigation),
                "peut_importer": autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, ecole)}
    catalogues = catalogues_visibles(ecole.catalogues_referentiels)
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "ajouter":
                contexte["url_saisie"] = request.POST.get("url", "")[:2000]
                catalogue = lire_catalogue_grist(contexte["url_saisie"])
                ecole = enregistrer_catalogue(ecole, request.user, catalogue["url"], catalogue=catalogue)
                contexte.update(catalogue_ajoute=catalogue, message="Catalogue disponible. Choisissez les référentiels à suivre.")
            elif action == "verifier":
                erreurs = []
                for cle, catalogue in catalogues.items():
                    if catalogue.get("url") and ecole.catalogues_referentiels.get(cle, {}).get("suivis"):
                        try:
                            actualise = lire_catalogue_grist(catalogue["url"])
                            ecole = enregistrer_catalogue(ecole, request.user, cle, catalogue=actualise)
                        except ValidationError as erreur:
                            erreurs.append(f'{catalogue["nom"]} — {" ".join(erreur.messages)}')
                contexte.update(erreurs_verification=erreurs, message="Vérification terminée.")
            elif action in {"suivre", "ne-plus-suivre"}:
                cle, reference = request.POST.get("catalogue"), request.POST.get("reference")
                if not any(ligne["reference"] == reference for ligne in catalogues.get(cle, {}).get("referentiels", [])):
                    raise ValidationError("Ce référentiel n’est plus proposé.")
                enregistrer_catalogue(ecole, request.user, cle, reference=reference, suivre=action == "suivre")
                return redirect(retour)
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            contexte["erreur"] = " ".join(erreur.messages)

    regles = ecole.catalogues_referentiels
    versions = {}
    for identifiant, numero in VersionReferentiel.objects.filter(
            Q(source__ecole=ecole) | Q(source__ecole__isnull=True)).values_list(
            "source__identifiant", "numero").order_by("pk"):
        versions.setdefault(identifiant, []).append(numero)
    lignes = []
    contexte["a_des_suivis"] = any(etat.get("suivis") for etat in regles.values())
    texte_recherche = slugify(q)
    termes = texte_recherche.split("-") if texte_recherche else []
    for cle, catalogue in catalogues_visibles(regles).items():
        for source in catalogue["referentiels"]:
            reference = source["reference"]
            url = catalogue.get("url")
            identifiant = identifiant_source_ecole(ecole, identite_grist(url, reference)) if url else source["identifiant_local"]
            locales = versions.get(identifiant, [])
            derniere = source["editions"][0]
            suivi = reference in regles.get(cle, {}).get("suivis", ())
            mise_a_jour = bool(locales) and str(derniere) not in locales
            ligne = {**source, "cle": cle, "catalogue": catalogue["nom"], "url": url,
                     "suivi": suivi, "locales": locales, "derniere": derniere, "mise_a_jour": mise_a_jour,
                     "locale": str(derniere) in locales}
            ajoute = contexte.get("catalogue_ajoute", {}).get("url") == cle
            if ajoute or (all(terme in slugify(f'{source["titre"]} {catalogue["nom"]}') for terme in termes)
                          and (filtre != "suivis" or suivi) and (filtre != "mises-a-jour" or mise_a_jour)):
                lignes.append(ligne)
    contexte["lignes"] = lignes
    return render(request, "suivi/decouvrir_referentiels.html", contexte)
