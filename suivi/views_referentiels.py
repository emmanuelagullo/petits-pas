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
