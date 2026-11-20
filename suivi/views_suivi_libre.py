from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .autorisations import MODIFIER_ETAT, charger_classe_autorisee, charger_eleve_autorise
from .catalogue_competences import doublons_classe
from .models import CompetenceLocale
from .navigation import ancrer_competence, filtre_competences, lien, retour_catalogue_ajout
from .forms_suivi_libre import ReussiteLibreForm, SelectionElevesForm
from .rubriques import contenu_classement
from .referentiels import adoption_courante, classe_historique
from .services.suivi_libre import ajouter_reussite, associer
from .services.medias_django import preparer_image
from .views import acces_requis
from .contexte_ecole import ecole_courante


@acces_requis
@require_http_methods(["GET", "POST"])
def suivi_libre(request, pk, locale_pk=None):
    classe = charger_classe_autorisee(request.user, pk, MODIFIER_ETAT, ecole=ecole_courante(request))
    filtre = filtre_competences(request)
    adoption = adoption_courante(classe)
    if not adoption or classe_historique(classe):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Préparez les choix d’une classe ouverte avant de saisir.")
    locale = get_object_or_404(CompetenceLocale, pk=locale_pk, ecole=classe.ecole,
                             suivi_libre=True) if locale_pk else None
    from .suivi_libre import peut_reprendre, reprises_ciblees_autorisees
    if locale and not peut_reprendre(request.user, classe, locale):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if locale and request.method == "GET" and locale.disponibilites.filter(classe=classe).exists():
        return redirect(lien("saisie_competence", classe.pk, locale.competence_id, filtre=filtre))
    initial = {"domaine": request.GET.get("domaine"), "sous_domaine": request.GET.get("sous_domaine")}
    if not locale:
        initial["reussite"] = request.GET.get("origine") != "catalogue" or request.GET.get("collectif") == "1"
        initial["libelle"] = request.GET.get("libelle", "")[:300]
        if filtre != "tous":
            initial["niveau"] = filtre
    if request.GET.get("collectif") == "1":
        initial["eleves"] = list(classe.eleves.values_list("pk", flat=True))
    eleve = None
    if request.GET.get("eleve"):
        eleve = charger_eleve_autorise(request.user, request.GET["eleve"], MODIFIER_ETAT, ecole=classe.ecole)
        if not eleve.scolarites.filter(classe=classe).exists():
            from django.http import Http404
            raise Http404
        initial.update(eleves=[eleve.pk], niveau=eleve.niveau, reussite=True)
    retour_catalogue = retour_catalogue_ajout(request, classe)
    attendu = {"classe": classe.pk, "compte": request.user.pk, "adoption": adoption.pk, "locale": locale_pk}
    initial["jeton"] = signing.dumps(attendu, salt="suivi-libre")
    options = dict(classe=classe, initial=initial)
    if not locale:
        options["contenu"] = contenu_classement(adoption)
    form = (SelectionElevesForm if locale else ReussiteLibreForm)(
        request.POST if request.method == "POST" else None, request.FILES or None, **options)
    doublons = []
    if request.method == "POST" and form.is_valid():
        try:
            if signing.loads(form.cleaned_data["jeton"], salt="suivi-libre", max_age=1800) != attendu:
                raise ValidationError("Les choix ont changé. Consultez à nouveau ce formulaire.")
            if locale:
                associer(utilisateur=request.user, classe=classe, locale=locale,
                    ids=form.cleaned_data["eleves"], adoption_attendue=adoption.pk,
                    retirer=request.POST.get("action") == "retirer")
                messages.success(request, "Disponibilité mise à jour, sans attribution de réussite.")
                if eleve and eleve.pk in form.cleaned_data["eleves"]:
                    return redirect(lien("saisie_eleve", eleve.pk, filtre=filtre, ancre=f"c{locale.competence_id}"))
                if retour_catalogue:
                    retour_catalogue = ancrer_competence(retour_catalogue, locale.competence_id)
                    if retour_catalogue.partition("?")[0].partition("#")[0] == lien("catalogue_competences", classe.pk):
                        return redirect(retour_catalogue)
                return redirect(lien("saisie_competence", classe.pk, locale.competence_id, filtre=filtre,
                                     **({"retour": retour_catalogue} if retour_catalogue else {})))
            d = form.cleaned_data
            if request.POST.get("confirmer_doublon") != "1":
                doublons = doublons_classe(classe, d["libelle"], request.user)
                if doublons:
                    raise ValidationError("Vérifiez la compétence existante avant de créer un doublon.")
            photo = preparer_image(d["photo"]) if d.get("photo") else None
            resultat = ajouter_reussite(utilisateur=request.user, classe=classe,
                ids=d["eleves"], domaine_id=d["domaine"], sous_domaine_id=d["sous_domaine"],
                libelle=d["libelle"], niveau=d["niveau"], date_observation=d["date_observation"],
                commentaire=d["commentaire"], photo=photo, adoption_attendue=adoption.pk, reussite=d["reussite"], icone=d["icone"])
            messages.success(request, "Compétence ajoutée au suivi des élèves sélectionnés.")
            if eleve:
                return redirect(lien("saisie_eleve", eleve.pk, filtre=filtre, ancre=f"c{resultat.competence_id}"))
            if retour_catalogue:
                retour_catalogue = ancrer_competence(retour_catalogue, resultat.competence_id)
                if retour_catalogue.partition("?")[0].partition("#")[0] == lien("catalogue_competences", classe.pk):
                    return redirect(retour_catalogue)
            return redirect(lien("saisie_competence", classe.pk, resultat.competence_id, filtre=filtre,
                                 **({"retour": retour_catalogue} if retour_catalogue else {})))
        except (signing.BadSignature, ValidationError) as exc:
            form.add_error(None, "Le formulaire a expiré. Consultez à nouveau cette page." if isinstance(exc, signing.BadSignature) else exc)
    reprises = reprises_ciblees_autorisees(request.user, classe).select_related("competence")
    return render(request, "suivi/suivi_libre.html", {"classe": classe, "form": form,
        "locale": locale, "reprises": reprises, "doublons": doublons, "eleve": eleve,
        "retour_catalogue": retour_catalogue, "selection_initiale": bool(initial.get("eleves"))})


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
    return redirect(lien("saisie_competence", classe.pk, locale.competence_id, filtre=filtre_competences(request)))
