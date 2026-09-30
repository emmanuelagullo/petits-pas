from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, charger_classe_autorisee
from .contexte_ecole import ecole_courante
from .referentiels import adoption_courante
from .services.adoption_bases_referentiels import adopter_base, apercu_adoption
from .services.choix_bases_referentiels import choix_bases
from .views import acces_requis


@acces_requis
@require_http_methods(["GET", "POST"])
def choisir_base_classe(request, classe_pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    choix = choix_bases(ecole, classe.annee_scolaire)
    actuelle = adoption_courante(classe)
    apercu, jeton, erreur = None, None, None
    if request.method == "POST":
        try:
            if request.POST.get("action") == "confirmer":
                try:
                    donnees = signing.loads(request.POST.get("jeton", ""), salt="base-classe", max_age=1800)
                except signing.BadSignature as cause:
                    raise ValidationError("L'aperçu a expiré ou n'est plus valable. Préparez un nouvel aperçu.") from cause
                if donnees["classe"] != classe.pk or donnees["auteur"] != request.user.pk:
                    raise ValidationError("Cet aperçu ne correspond pas à votre classe.")
                adopter_base(utilisateur=request.user, classe=classe, version_id=donnees["version"],
                    revisions_attendues=donnees["revisions"], adoption_attendue=donnees["adoption"])
                messages.success(request, "La base de la classe est choisie. Aucune réussite n'a été créée ou transférée.")
                return redirect("classe_detail", pk=classe.pk)
            if request.POST.get("action") != "apercu":
                raise ValidationError("Choisissez une base et consultez son aperçu.")
            try:
                version_id = int(request.POST.get("version", ""))
            except ValueError as cause:
                raise ValidationError("Choisissez une base autorisée.") from cause
            apercu = apercu_adoption(utilisateur=request.user, classe=classe, version_id=version_id)
            jeton = signing.dumps({"classe": classe.pk, "auteur": request.user.pk,
                "version": version_id, "revisions": apercu["revisions"], "adoption": apercu["adoption_id"]}, salt="base-classe")
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    disponibles = {v.pk for v in choix.versions}
    selection_id = actuelle.version_id if actuelle and actuelle.version_id in disponibles else (choix.proposee.pk if choix.proposee else None)
    return render(request, "suivi/choisir_base_classe.html", {"classe": classe, "choix": choix,
        "actuelle": actuelle, "selection_id": selection_id, "apercu": apercu, "jeton": jeton, "erreur": erreur}, status=400 if erreur else 200)


@acces_requis
@require_http_methods(["GET", "POST"])
def choisir_bases_ecole(request):
    from django.core.exceptions import PermissionDenied
    from django.urls import reverse
    from django.utils import timezone

    from .autorisations import GERER_REFERENTIEL_ECOLE, autorise
    from .forms_referentiels import ChoixEcoleForm
    from .models import ChoixApplicationAnnuel, ChoixEcoleAnnuel, annee_scolaire_pour
    from .services.choix_bases_referentiels import (apercu_choix_ecole, choix_superieurs,
                                                  enregistrer_choix_ecole, verifier_annee)

    ecole = ecole_courante(request)
    if not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    courante = annee_scolaire_pour(timezone.localdate())
    annee = (request.POST if request.method == "POST" else request.GET).get("annee", courante)
    debut = int(courante[:4])
    annees = sorted({courante, f"{debut + 1}-{debut + 2}"}
        | set(ecole.classes.values_list("annee_scolaire", flat=True))
        | set(ChoixEcoleAnnuel.objects.filter(ecole=ecole).values_list("annee_scolaire", flat=True))
        | set(ChoixApplicationAnnuel.objects.values_list("annee_scolaire", flat=True)), reverse=True)
    contexte = {"annee": annee, "annees": annees}
    try:
        verifier_annee(annee)
    except ValidationError as cause:
        contexte["erreur"] = " ".join(cause.messages)
        return render(request, "suivi/choisir_bases_ecole.html", contexte, status=400)
    superieures, proposee_superieure = choix_superieurs(ecole, annee)
    choix = choix_bases(ecole, annee)
    local = ChoixEcoleAnnuel.objects.filter(ecole=ecole, annee_scolaire=annee).first()
    initial = {"autorisations": "restreindre" if local and local.restreindre else "garder",
        "versions": list(local.versions_autorisees.values_list("pk", flat=True)) if local else [],
        "proposee": local.version_proposee_id if local else None}
    form = ChoixEcoleForm(versions=superieures, initial=initial)
    apercu, jeton, erreur = None, None, None
    if request.method == "POST":
        try:
            if request.POST.get("action") == "confirmer":
                try:
                    donnees = signing.loads(request.POST.get("jeton", ""), salt="bases-ecole", max_age=1800)
                except signing.BadSignature as cause:
                    raise ValidationError("L'aperçu a expiré ou n'est plus valable. Préparez un nouvel aperçu.") from cause
                if donnees["ecole"] != ecole.pk or donnees["auteur"] != request.user.pk or donnees["annee"] != annee:
                    raise ValidationError("Cet aperçu ne correspond pas à votre école ou à l'année choisie.")
                enregistrer_choix_ecole(utilisateur=request.user, ecole=ecole, annee=annee,
                    restreindre=donnees["restreindre"], versions_ids=donnees["versions_ids"],
                    proposee_id=donnees["proposee_id"], revisions_attendues=donnees["revisions"])
                messages.success(request, "Les choix de l'école sont enregistrés pour cette année. Les bases des classes et leurs observations sont conservées.")
                return redirect(f"{reverse('referentiels_ecole')}?annee={annee}")
            if request.POST.get("action") != "apercu":
                raise ValidationError("Consultez les conséquences avant de confirmer.")
            form = ChoixEcoleForm(request.POST, versions=superieures)
            if not form.is_valid():
                raise ValidationError("Vérifiez les bases choisies.")
            apercu = apercu_choix_ecole(utilisateur=request.user, ecole=ecole, annee=annee,
                restreindre=form.cleaned_data["restreindre"], versions_ids=form.cleaned_data["versions"],
                proposee_id=form.cleaned_data["proposee"])
            jeton = signing.dumps({"ecole": ecole.pk, "auteur": request.user.pk, "annee": annee,
                **{cle: apercu[cle] for cle in ("restreindre", "versions_ids", "proposee_id", "revisions")}}, salt="bases-ecole")
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    contexte.update(form=form, choix=choix, proposee_superieure=proposee_superieure,
        apercu=apercu, jeton=jeton, erreur=erreur)
    return render(request, "suivi/choisir_bases_ecole.html", contexte, status=400 if erreur else 200)
