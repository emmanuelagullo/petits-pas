from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .autorisations import MODIFIER_ETAT, charger_classe_autorisee, charger_eleve_autorise
from .models import CompetenceLocale
from .forms_suivi_libre import ReussiteLibreForm, SelectionElevesForm
from .referentiels import adoption_courante, contenu_origine, classe_historique
from .services.suivi_libre import ajouter_reussite, associer
from .services.medias_django import preparer_image
from .views import acces_requis
from .contexte_ecole import ecole_courante


@acces_requis
@require_http_methods(["GET", "POST"])
def suivi_libre(request, pk, locale_pk=None):
    classe = charger_classe_autorisee(request.user, pk, MODIFIER_ETAT, ecole=ecole_courante(request))
    adoption = adoption_courante(classe)
    if not adoption or classe_historique(classe):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Préparez les choix d’une classe ouverte avant de saisir.")
    locale = get_object_or_404(CompetenceLocale, pk=locale_pk, ecole=classe.ecole,
                             suivi_libre=True) if locale_pk else None
    from .suivi_libre import peut_reprendre
    if locale and not peut_reprendre(request.user, classe, locale):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if locale and request.method == "GET":
        from .referentiels import competence_classe
        if competence_classe(classe, locale.competence):
            return redirect("saisie_competence", pk=classe.pk, competence_pk=locale.competence_id)
    initial = {"domaine": request.GET.get("domaine"), "sous_domaine": request.GET.get("sous_domaine")}
    eleve = None
    if request.GET.get("eleve"):
        eleve = charger_eleve_autorise(request.user, request.GET["eleve"], MODIFIER_ETAT, ecole=classe.ecole)
        if not eleve.scolarites.filter(classe=classe).exists():
            from django.http import Http404
            raise Http404
        initial.update(eleves=[eleve.pk], niveau=eleve.niveau, reussite=True)
    attendu = {"classe": classe.pk, "compte": request.user.pk, "adoption": adoption.pk, "locale": locale_pk}
    initial["jeton"] = signing.dumps(attendu, salt="suivi-libre")
    options = dict(classe=classe, initial=initial)
    if not locale:
        options["contenu"] = contenu_origine(adoption)
    form = (SelectionElevesForm if locale else ReussiteLibreForm)(
        request.POST if request.method == "POST" else None, request.FILES or None, **options)
    if request.method == "POST" and form.is_valid():
        try:
            if signing.loads(form.cleaned_data["jeton"], salt="suivi-libre", max_age=1800) != attendu:
                raise ValidationError("Les choix ont changé. Consultez à nouveau ce formulaire.")
            if locale:
                associer(utilisateur=request.user, classe=classe, locale=locale,
                    ids=form.cleaned_data["eleves"], adoption_attendue=adoption.pk,
                    retirer=request.POST.get("action") == "retirer")
                messages.success(request, "Disponibilité mise à jour, sans attribution de réussite.")
                return redirect("saisie_competence", pk=classe.pk, competence_pk=locale.competence_id)
            d = form.cleaned_data
            photo = preparer_image(d["photo"]) if d.get("photo") else None
            resultat = ajouter_reussite(utilisateur=request.user, classe=classe,
                ids=d["eleves"], domaine_id=d["domaine"], sous_domaine_id=d["sous_domaine"],
                libelle=d["libelle"], niveau=d["niveau"], date_observation=d["date_observation"],
                commentaire=d["commentaire"], photo=photo, adoption_attendue=adoption.pk, reussite=d["reussite"], icone=d["icone"])
            messages.success(request, "Compétence ajoutée au suivi des élèves sélectionnés.")
            if eleve:
                return redirect("saisie_eleve", pk=eleve.pk)
            return redirect("saisie_competence", pk=classe.pk, competence_pk=resultat.competence_id)
        except (signing.BadSignature, ValidationError) as exc:
            form.add_error(None, "Le formulaire a expiré. Consultez à nouveau cette page." if isinstance(exc, signing.BadSignature) else exc)
    reprises = CompetenceLocale.objects.filter(ecole=classe.ecole, suivi_libre=True).select_related("competence")
    reprises = [c for c in reprises if peut_reprendre(request.user, classe, c)]
    return render(request, "suivi/suivi_libre.html", {"classe": classe, "form": form,
        "locale": locale, "reprises": reprises, "eleve": eleve})


@acces_requis
@require_http_methods(["POST"])
def activer_suivi(request, pk, locale_pk, eleve_pk):
    classe = charger_classe_autorisee(request.user, pk, MODIFIER_ETAT, ecole=ecole_courante(request))
    locale = get_object_or_404(CompetenceLocale, pk=locale_pk, ecole=classe.ecole, suivi_libre=True)
    adoption = adoption_courante(classe)
    if not adoption or classe_historique(classe):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if request.POST.get("action") not in ("activer", "desactiver"):
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Action inconnue.")
    try:
        associer(utilisateur=request.user, classe=classe, locale=locale, ids=[eleve_pk],
                 adoption_attendue=int(request.POST.get("adoption", 0)),
                 retirer=request.POST["action"] == "desactiver")
    except (ValidationError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("saisie_competence", pk=classe.pk, competence_pk=locale.competence_id)
