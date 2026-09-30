"""Relier des apprentissages avec explication, sans toucher aux suivis."""
from hashlib import sha256
import json

from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, VOIR_CLASSE,
                           autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .correspondances_referentiels import correspondances_classe, instantane_lien, liens_actifs
from .forms_referentiels import CorrespondanceCompetenceForm
from .models import CorrespondanceCompetence, annee_scolaire_pour
from .referentiels import adoption_courante
from .services.correspondances_referentiels import catalogue_liens, relier_competences, retirer_correspondance
from .services.choix_bases_referentiels import verifier_annee
from .views import acces_requis


@acces_requis
@require_http_methods(["GET", "POST"])
def correspondances(request, classe_pk=None):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, VOIR_CLASSE, ecole=ecole) if classe_pk else None
    modifier = autorise(request.user, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                       classe if classe else ecole)
    if not classe and not modifier:
        raise PermissionDenied
    annee = classe.annee_scolaire if classe else request.GET.get("annee", annee_scolaire_pour(timezone.localdate()))
    try:
        verifier_annee(annee)
    except ValidationError as cause:
        return render(request, "suivi/correspondances_referentiels.html", {"erreur": " ".join(cause.messages)}, status=400)
    adoption = adoption_courante(classe)
    clos = bool(adoption and adoption.clos)
    ouvert = modifier and (not classe or bool(adoption and not clos))
    catalogue = catalogue_liens(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe) if ouvert else {}
    perimetre = Q(classe__isnull=True) | Q(classe=classe) if classe else Q(classe__isnull=True)
    revisions = list(CorrespondanceCompetence.objects.filter(perimetre, ecole=ecole,
        annee_scolaire=annee).order_by("pk").values_list("pk", "revision", "active"))
    contexte = {"auteur": request.user.pk, "ecole": ecole.pk, "annee": annee,
        "classe": classe.pk if classe else None, "adoption": adoption.pk if adoption else None,
        "liens": sha256(json.dumps(revisions).encode()).hexdigest()}
    initial = {}
    try:
        competence_id = int(request.GET.get("competence", ""))
    except ValueError:
        competence_id = None
    if competence_id:
        candidats = [(r, c) for r, c in catalogue.items() if c["competence_id"] == competence_id]
        candidats.sort(key=lambda paire: paire[1]["version_id"] != (adoption.version_id if adoption else None))
        if candidats:
            initial["depart"] = candidats[0][0]
    form = CorrespondanceCompetenceForm(catalogue=catalogue, initial=initial) if ouvert else None
    erreur, perime = None, False
    if request.method == "POST":
        if not modifier:
            raise PermissionDenied
        try:
            if not ouvert:
                raise ValidationError("Choisissez une base pour une classe ouverte avant de modifier les liens.")
            try:
                donnees = signing.loads(request.POST.get("jeton", ""), salt="correspondances", max_age=1800)
            except signing.BadSignature as cause:
                perime = True
                raise ValidationError("Cette page a expiré. Reconsultez les correspondances.") from cause
            if donnees != contexte:
                perime = True
                raise ValidationError("La base ou les liens ont changé. Reconsultez les correspondances.")
            if request.POST.get("action") == "relier":
                form = CorrespondanceCompetenceForm(request.POST, catalogue=catalogue)
                if not form.is_valid():
                    raise ValidationError("Vérifiez les deux compétences, le sens du lien et votre explication.")
                relier_competences(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                    adoption_attendue=contexte["adoption"], reference_depart=form.cleaned_data["depart"],
                    reference_arrivee=form.cleaned_data["arrivee"], type_lien=form.cleaned_data["type_lien"],
                    justification=form.cleaned_data["justification"])
            elif request.POST.get("action") == "retirer":
                try:
                    lien_id, revision = int(request.POST.get("lien", "")), int(request.POST.get("revision", ""))
                except ValueError as cause:
                    raise ValidationError("Reconsultez le lien à retirer.") from cause
                retirer_correspondance(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                    adoption_attendue=contexte["adoption"], lien_id=lien_id, revision_attendue=revision)
            else:
                raise ValidationError("Choisissez une action proposée sur cette page.")
            messages.success(request, "Correspondance enregistrée. Les observations et réussites restent inchangées.")
            return redirect(reverse("correspondances_classe", args=[classe.pk]) if classe else reverse("correspondances_ecole") + "?annee=" + annee)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    liens = correspondances_classe(classe) if classe else [instantane_lien(l) for l in liens_actifs(ecole, annee)]
    for lien in liens:
        lien["retirable"] = ouvert and lien["classe_id"] == (classe.pk if classe else None)
    return render(request, "suivi/correspondances_referentiels.html", {"classe": classe, "annee": annee,
        "ouvert": ouvert, "clos": clos, "modifier": modifier, "form": form, "liens": liens,
        "erreur": erreur, "jeton": signing.dumps(contexte, salt="correspondances") if ouvert and not perime else None},
        status=400 if erreur else 200)
