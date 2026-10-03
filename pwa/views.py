"""Adaptation d'impression sans moteur PDF natif ni accès médias supplémentaire."""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe, require_http_methods
from django.template.loader import render_to_string
from suivi.autorisations import GENERER_CARNET
from django.utils.safestring import mark_safe
from suivi.views import (
    acces_requis, direction_requise, _contexte_carnet, _contexte_grille_competence,
    preparer_edition, ecole_courante, charger_classe_autorisee,
)


def contexte(request):
    return {"mode_pwa": True}


@never_cache
@acces_requis
@require_safe
def carnet_imprimable(request, pk):
    return render(request, "suivi/carnet.html", {
        **_contexte_carnet(request, pk, operation=GENERER_CARNET),
        "impression_pwa": True,
    })


@never_cache
@acces_requis
@require_safe
def grille_imprimable(request, pk, competence_pk):
    return render(request, "suivi/grille_competence.html", {
        **_contexte_grille_competence(request, pk, competence_pk, GENERER_CARNET),
        "impression_pwa": True,
    })


# En fonctionnement normal, l'export complet reste réservé à la direction.
@never_cache
@direction_requise
@require_safe
def autoriser_recuperation(request):
    return HttpResponse(status=204)


@never_cache
@acces_requis
@require_http_methods(["GET", "POST"])
def edition_imprimable(request, pk):
    if request.method == "GET":
        return preparer_edition(request, pk)
    classe = charger_classe_autorisee(
        request.user, pk, GENERER_CARNET, ecole=ecole_courante(request)
    )
    selection = list(classe.eleves.filter(pk__in=request.POST.getlist("eleves")))
    if not selection:
        messages.error(request, "Sélectionnez au moins un enfant.")
        # Le GET commun conserve les mêmes choix de présentation.
        return redirect("preparer_edition", pk=pk)
    options = {key: request.POST.get(key, default) for key, default in [
        ("contenu", "observes"), ("colonnes", "2"), ("regroupement", "aucun"),
    ]}
    options.update({key: "1" if key in request.POST else "0"
                    for key in ["attendus", "sous_domaines", "bilans"]})
    carnets = []
    for eleve in selection:
        context = _contexte_carnet(request, eleve.pk, options, GENERER_CARNET)
        # Le fragment provient exclusivement du template commun, qui échappe
        # les textes utilisateurs ; aucun HTML reçu dans le POST n'est accepté.
        carnets.append(mark_safe(render_to_string(
            "suivi/partiels/carnet_contenu.html", context, request=request
        )))
    return render(request, "pwa/edition_imprimable.html", {"carnets": carnets})
