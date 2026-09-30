import mimetypes

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .autorisations import ADMINISTRER_ECOLE, MODIFIER_ETAT, VOIR_SUIVI, autorise, charger_classe_autorisee, classes_accessibles
from .contexte_ecole import ecole_courante
from .forms_presentation import IllustrationForm
from .models import Competence, ParametresCarnet, ReglagePresentation
from .referentiels import arbre_competences, competence_classe
from .presentation import catalogue_icones, illustration_effective, propositions
from .services.presentation import enregistrer_formulation, enregistrer_reglage, verifier_droit
from .views import acces_requis, _supprimer_media_apres_validation


def url_illustration(illustration):
    if illustration.photo:
        return reverse("media_presentation", args=[illustration.reglage_id])
    return static(illustration.statique) if illustration.statique else ""


def _perimetre(request, classe_pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, MODIFIER_ETAT, ecole=ecole) if classe_pk else None
    verifier_droit(request.user, ecole, classe)
    return ecole, classe


@acces_requis
def regler_presentation(request, classe_pk=None, competence_pk=None):
    ecole = ecole_courante(request)
    if classe_pk is None and not autorise(request.user, ADMINISTRER_ECOLE, ecole):
        # Ne pas deviner une classe : l'utilisateur choisit explicitement
        # le périmètre de ses réglages, sans ouvrir les réglages de l'école.
        competence = Competence.objects.filter(pk=competence_pk, domaine__ecole=ecole).first() if competence_pk else None
        destinations = []
        for classe in classes_accessibles(request.user, MODIFIER_ETAT, ecole=ecole):
            url = (reverse("presentation_competence_classe", args=[classe.pk, competence.pk])
                   if competence else reverse("presentation_classe", args=[classe.pk]))
            destinations.append({"classe": classe, "url": url})
        return render(request, "suivi/presentation_acces_refuse.html",
                      {"destinations": destinations}, status=403)
    ecole, classe = _perimetre(request, classe_pk)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole) if competence_pk else None
    if classe and competence:
        competence = competence_classe(classe, competence) or competence
    filtres = {"ecole": ecole, "classe": classe, "competence": competence}
    reglage = ReglagePresentation.objects.filter(**filtres).first() or ReglagePresentation(**filtres)
    ancien_nom = reglage.photo.name if reglage.photo else ""
    form = IllustrationForm(instance=reglage)
    erreur = None
    if request.method == "POST":
        action = request.POST.get("action", "illustration")
        try:
            if action == "illustration":
                form = IllustrationForm(request.POST, request.FILES, instance=reglage)
                if form.is_valid():
                    enregistrer_reglage(request.user, form.save(commit=False))
                    if ancien_nom and ancien_nom != (reglage.photo.name if reglage.photo else ""):
                        _supprimer_media_apres_validation(ancien_nom)
                else:
                    raise ValidationError("Vérifiez le choix d'illustration.")
            elif action in {"formulation", "ajouter_formulation"} and competence:
                enregistrer_formulation(
                    utilisateur=request.user, competence=competence, classe=classe,
                    cle=request.POST.get("cle") if action == "formulation" else None,
                    mode=request.POST.get("mode", "remplacer"), texte=request.POST.get("texte", ""),
                )
            else:
                raise Http404
            messages.success(request, "Réglage de présentation enregistré.")
            return redirect(request.path)
        except ValidationError as exc:
            erreur = " ".join(exc.messages)
    illustration = illustration_effective(ecole, competence, classe)
    if classe:
        index_url = reverse("presentation_classe", args=[classe.pk])
    else:
        index_url = reverse("presentation_ecole")
    domaines = []
    if not competence:
        for domaine in arbre_competences(ecole, classe=classe):
            lignes = []
            for c in domaine.visibles:
                url = reverse("presentation_competence_classe", args=[classe.pk, c.pk]) if classe else reverse("presentation_competence_ecole", args=[c.pk])
                lignes.append({"competence": c, "url": url})
            if lignes:
                domaines.append((domaine, lignes))
    parametres, _ = ParametresCarnet.objects.get_or_create(ecole=ecole)
    return render(request, "suivi/presentation.html", {
        "ecole": ecole, "classe": classe, "competence": competence,
        "form": form, "erreur": erreur, "illustration": illustration,
        "illustration_url": url_illustration(illustration), "index_url": index_url,
        "domaines": domaines,
        "afficher_sous_domaines": parametres.afficher_sous_domaines,
        "icones_apercu": {cle: static(valeur["fichier"]) for cle, valeur in catalogue_icones().items()},
        "propositions": propositions(competence, classe, inclure_masquees=True) if competence else [],
    })


@never_cache
@acces_requis
@require_safe
def media_presentation(request, pk):
    ecole = ecole_courante(request)
    reglage = get_object_or_404(ReglagePresentation, pk=pk, ecole=ecole,
                              mode=ReglagePresentation.REMPLACER)
    if not reglage.photo:
        raise Http404
    if not autorise(request.user, ADMINISTRER_ECOLE, ecole):
        if reglage.classe_id:
            permis = autorise(request.user, VOIR_SUIVI, reglage.classe, ecole=ecole)
        else:
            permis = classes_accessibles(request.user, VOIR_SUIVI, ecole=ecole).exists()
        if not permis:
            raise Http404
    return FileResponse(default_storage.open(reglage.photo.name, "rb"),
                        content_type=mimetypes.guess_type(reglage.photo.name)[0] or "application/octet-stream")
