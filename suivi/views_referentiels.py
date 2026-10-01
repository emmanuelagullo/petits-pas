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
                    revisions_attendues=donnees["revisions"], adoption_attendue=donnees["adoption"],
                    adaptations_attendues=donnees.get("adaptations"), garde_attendue=donnees.get("garde"))
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
                "version": version_id, "revisions": apercu["revisions"], "adoption": apercu["adoption_id"],
                "garde": apercu["garde"]["empreinte"],
                "adaptations": apercu["mise_a_jour"]["empreinte_adaptations"] if apercu["mise_a_jour"] else None}, salt="base-classe")
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


@acces_requis
@require_http_methods(["GET", "POST"])
def adapter_competences(request, classe_pk=None, competence_pk=None):
    from copy import deepcopy
    from django.core.exceptions import PermissionDenied
    from django.http import Http404
    from django.shortcuts import get_object_or_404
    from django.urls import reverse
    from django.utils import timezone

    from .adaptations_referentiels import contenu_adapte, contenus_ecole
    from .autorisations import GERER_REFERENTIEL_ECOLE, autorise
    from .forms_referentiels import AdaptationCompetenceForm
    from .models import AdaptationCompetence, AdoptionReferentiel, Competence, annee_scolaire_pour
    from .referentiels import arbre_version, contenu_adoption, contenu_origine
    from .services.adaptations_referentiels import enregistrer_adaptation
    from .services.choix_bases_referentiels import verifier_annee

    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole) if classe_pk else None
    if not classe and not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    actuelle = adoption_courante(classe)
    valeurs = request.POST if request.method == "POST" else request.GET
    annee = classe.annee_scolaire if classe else valeurs.get("annee", annee_scolaire_pour(timezone.localdate()))
    try:
        verifier_annee(annee)
    except ValidationError as cause:
        return render(request, "suivi/adapter_competences.html", {"classe": classe, "annee": annee,
            "erreur": " ".join(cause.messages)}, status=400)
    if classe:
        bases = []
        deja = set()
        for adoption in AdoptionReferentiel.objects.filter(classe=classe).select_related("version__source").order_by("-courante", "-pk"):
            if adoption.version_id not in deja:
                bases.append((adoption.version, contenu_origine(adoption)))
                deja.add(adoption.version_id)
    else:
        bases = contenus_ecole(ecole, annee)
    try:
        version_id = int(valeurs.get("version", bases[0][0].pk if bases else 0))
    except (TypeError, ValueError):
        raise Http404
    selection = next((paire for paire in bases if paire[0].pk == version_id), None)
    if selection is None and (version_id or competence_pk):
        raise Http404
    version, origine = selection if selection else (None, {})
    clos = bool(actuelle and actuelle.clos)
    hors_base = bool(classe and actuelle and version_id != actuelle.version_id)
    if clos:
        effectif = deepcopy(origine)
        finales = {c["id"]: c for c in contenu_adoption(actuelle).get("competences", [])}
        for definition in effectif.get("competences", []):
            definition.update(finales.get(definition["id"], {}))
    else:
        effectif = contenu_adapte(ecole, annee, origine, classe)
    index_url = reverse("adaptations_classe", args=[classe.pk]) if classe else reverse("adaptations_ecole")
    suffixe = f"?annee={annee}&version={version_id}"
    contexte = {"classe": classe, "annee": annee, "bases": [v for v, _ in bases], "version": version,
                "clos": clos, "hors_base": hors_base, "index_url": index_url + suffixe}
    if not competence_pk:
        if request.method == "POST":
            raise Http404
        ids = [c["id"] for c in effectif.get("competences", [])]
        domaines = arbre_version(ecole, effectif, inclure_ids=ids, masquer=False, masque_actuel=False)
        for domaine in domaines:
            for competence in domaine.visibles:
                competence.url_adaptation = (reverse("adaptation_competence_classe", args=[classe.pk, competence.pk])
                    if classe else reverse("adaptation_competence_ecole", args=[competence.pk])) + suffixe
        contexte["domaines"] = domaines
        return render(request, "suivi/adapter_competences.html", contexte)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    definition = next((c for c in origine.get("competences", []) if c["id"] == competence.pk), None)
    if definition is None:
        raise Http404
    courante = next(c for c in effectif["competences"] if c["id"] == competence.pk)
    proposee = next(c for c in contenu_adapte(ecole, annee, origine)["competences"] if c["id"] == competence.pk) if classe else definition
    if not classe:
        proposee = {**definition, "active": definition["active"] and competence.active}
    regle = AdaptationCompetence.objects.filter(ecole=ecole, annee_scolaire=annee,
                                               classe=classe, competence=competence).first()
    initial = {"mode_libelle": "personnel" if regle and regle.libelle is not None else "garder",
        "libelle": regle.libelle if regle and regle.libelle is not None else proposee["libelle"],
        "visibilite": "garder" if not regle or regle.visible is None else ("montrer" if regle.visible else "masquer")}
    form = AdaptationCompetenceForm(initial=initial)
    attente = {"ecole": ecole.pk, "auteur": request.user.pk, "annee": annee,
        "classe": classe.pk if classe else None, "competence": competence.pk, "version": version_id,
        "revision": regle.revision if regle else 0, "adoption": actuelle.pk if actuelle else None}
    erreur = None
    jeton = signing.dumps(attente, salt="adaptation-competence")
    if request.method == "POST":
        jeton = None
        form = AdaptationCompetenceForm(request.POST)
        try:
            try:
                signe = signing.loads(request.POST.get("jeton", ""), salt="adaptation-competence", max_age=1800)
            except signing.BadSignature as cause:
                raise ValidationError("Les choix ont expiré ou ne sont plus valables. Consultez à nouveau la compétence.") from cause
            if signe != attente:
                raise ValidationError("Les choix ou la base ont changé. Consultez à nouveau la compétence.")
            jeton = signing.dumps(attente, salt="adaptation-competence")
            if not form.is_valid():
                raise ValidationError("Vérifiez votre libellé et les choix de visibilité.")
            enregistrer_adaptation(utilisateur=request.user, ecole=ecole, annee=annee,
                competence=competence, classe=classe, libelle=form.cleaned_data["libelle"],
                visible=form.cleaned_data["visible"],
                revision_attendue=signe["revision"], adoption_attendue=signe["adoption"])
            messages.success(request, "Les choix de cette compétence sont enregistrés pour l'année. Son identité et ses observations sont conservées.")
            return redirect(request.path + suffixe)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    contexte.update(competence=competence, origine=definition, courante=courante, proposee=proposee,
                    form=form, erreur=erreur, jeton=jeton, consultation_url=request.path + suffixe)
    return render(request, "suivi/adapter_competences.html", contexte, status=400 if erreur else 200)
