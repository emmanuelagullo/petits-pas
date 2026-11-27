from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .views import acces_requis


@acces_requis
@require_POST
def affichage_licences(request):
    visible = request.POST.get("visible") == "1"
    request.session["afficher_licences"] = visible
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"visible": visible})
    retour = request.POST.get("retour", "")
    if not url_has_allowed_host_and_scheme(retour, {request.get_host()}, require_https=request.is_secure()):
        retour = ""
    return redirect(retour or reverse("accueil"))


@acces_requis
@require_POST
def politique_licence(request, classe_pk=None):
    from django.core.exceptions import PermissionDenied
    from .autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise, charger_classe_autorisee
    from .contexte_ecole import ecole_courante

    ecole = ecole_courante(request)
    if classe_pk is None:
        if not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
            raise PermissionDenied
        objet = ecole
        retour = reverse("referentiels_ecole")
    else:
        objet = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
        retour = reverse("referentiel_classe", args=[classe_pk])
    mode = request.POST.get("mode", "")
    if mode not in {"", "referentiel", "licence"}:
        raise PermissionDenied
    licence = request.POST.get("licence", "").strip()[:120]
    objet.politique_licence = (licence or "CC-BY-SA-4.0") if mode == "licence" else mode
    objet.save(update_fields=["politique_licence"])
    return redirect(retour)
