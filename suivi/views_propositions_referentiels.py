from django import forms
from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise, charger_classe_autorisee
from .contexte_ecole import ecole_courante
from .models import Classe, Ecole, PropositionReferentiel
from .services.choix_bases_referentiels import choix_bases
from .services.import_sources_referentiels import importer_source
from .services.paquets_referentiels import MAX_ARCHIVE, lire_paquet
from .views import acces_requis
from .views_paquets_referentiels import (
    SEL as SEL_IMPORT, apercu_document, informations_partage, presenter_contenu_partage,
)
from .navigation import lien
from .referentiels import adoption_courante
from .services.partage_referentiel_classe import resoudre_licences_classe

SEL = "proposition-referentiel"


class NoteProposition(forms.Form):
    note = forms.CharField(label="Note à la direction (facultatif)", max_length=500, required=False,
                           help_text="Évitez les noms d’élèves et les informations individuelles.")


@acces_requis
@require_http_methods(["GET", "POST"])
def proposer_classe(request, classe_pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    if classe.etat != Classe.ACTIVE:
        raise PermissionDenied
    propositions = PropositionReferentiel.objects.filter(classe=classe, auteur=request.user).defer("document")
    retour_competences = lien("catalogue_competences", classe.pk, ancre="actions-referentiel-classe")
    retour_import = lien("paquets_referentiels_classe", classe.pk, volet="importer",
                         destination="classe", reprendre=1, ancre="import-referentiel")
    contexte = {"classe": classe, "propositions": propositions,
                "retour_competences": retour_competences, "retour_import": ""}
    try:
        if request.method == "POST":
            action = request.POST.get("action")
            origine = ""
            if action == "examiner-classe":
                origine = "classe"
                adoption = adoption_courante(classe)
                if not adoption or adoption.clos:
                    raise ValidationError("Choisissez d’abord le référentiel de la classe.")
                donnees, _ = informations_partage(classe, adoption)
                donnees = dict(donnees)
                brut, _, _ = presenter_contenu_partage(classe, {}, donnees)
                donnees["licence"] = resoudre_licences_classe(adoption, brut)
                _, paquet, _ = presenter_contenu_partage(classe, {}, donnees)
                document = lire_paquet(paquet)
            elif action == "examiner":
                fichier = request.FILES.get("paquet")
                if not fichier:
                    raise ValidationError("Choisissez le fichier à examiner.")
                document = lire_paquet(fichier.read(MAX_ARCHIVE + 1))
            elif action == "reprendre-apercu":
                preparation = request.session.get(SEL_IMPORT, {})
                try:
                    attendu = signing.loads(request.POST.get("jeton_import", ""), salt=SEL_IMPORT, max_age=1800)
                except signing.BadSignature as cause:
                    raise ValidationError("Examinez de nouveau l’édition avant de la proposer.") from cause
                if attendu != preparation.get("jeton") or any(
                    attendu.get(cle) != valeur for cle, valeur in {
                        "auteur": request.user.pk, "classe": classe.pk, "ecole": ecole.pk,
                        "annee": classe.annee_scolaire, "import_classe": True,
                    }.items()
                ):
                    raise ValidationError("Le contexte de l’import a changé.")
                origine = "zip"
                contexte["retour_import"] = retour_import
                document = preparation["document"]
            if action in {"examiner-classe", "examiner", "reprendre-apercu"}:
                importer_source(document, verifier_seulement=True, ecole=ecole)
                jeton = get_random_string(32)
                request.session[SEL] = {
                    "jeton": jeton, "classe": classe.pk, "auteur": request.user.pk,
                    "document": document, "origine": origine,
                }
                contexte.update(apercu_document(document, ecole), jeton=jeton, note=NoteProposition())
            elif action == "proposer":
                preparation = request.session.get(SEL, {})
                if (preparation.get("jeton"), preparation.get("classe"), preparation.get("auteur")) != (
                        request.POST.get("jeton"), classe.pk, request.user.pk):
                    raise ValidationError("Examinez de nouveau le fichier avant de le proposer.")
                if preparation.get("origine") == "zip":
                    contexte["retour_import"] = retour_import
                document = preparation["document"]
                apercu = apercu_document(document, ecole)
                note = NoteProposition(request.POST)
                if note.is_valid():
                    with transaction.atomic():
                        Ecole.objects.select_for_update().get(pk=ecole.pk)
                        importer_source(document, verifier_seulement=True, ecole=ecole)
                        PropositionReferentiel.objects.get_or_create(
                            classe=classe, auteur=request.user, document=document, etat=PropositionReferentiel.ATTENTE,
                            defaults={"titre": apercu["apercu"]["source"]["titre"], "numero": apercu["apercu"]["version"],
                                      "note": note.cleaned_data["note"]},
                        )
                    request.session.pop(SEL, None)
                    messages.success(request, "La proposition est disponible pour la direction.")
                    if preparation.get("origine") == "classe":
                        return redirect(lien("catalogue_competences", classe.pk, ancre="actions-referentiel-classe"))
                    if preparation.get("origine") == "zip":
                        return redirect(retour_import)
                    return redirect("proposer_referentiel_classe", classe_pk=classe.pk)
                contexte.update(apercu, jeton=preparation["jeton"], note=note)
            else:
                raise ValidationError("Action inconnue.")
    except ValidationError as erreur:
        contexte["erreur"] = " ".join(erreur.messages)
    return render(request, "suivi/proposer_referentiel.html", contexte, status=400 if "erreur" in contexte else 200)


@acces_requis
@require_http_methods(["GET", "POST"])
def propositions_ecole(request, pk=None):
    ecole = ecole_courante(request)
    if not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    propositions = PropositionReferentiel.objects.filter(classe__ecole=ecole).select_related("classe", "auteur")
    if pk is None:
        if request.method == "POST":
            raise PermissionDenied
        return render(request, "suivi/propositions_referentiels.html", {"propositions": propositions.defer("document"), "annee": request.GET.get("annee", "")})
    proposition = get_object_or_404(propositions, pk=pk)
    contexte = {"proposition": proposition, "retour_propositions": lien(
        "propositions_referentiels_ecole", annee=proposition.classe.annee_scolaire,
    )}
    if request.method == "POST":
        try:
            with transaction.atomic():
                ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
                if not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
                    raise PermissionDenied
                proposition = get_object_or_404(propositions.select_for_update(), pk=pk)
                if proposition.etat != PropositionReferentiel.ATTENTE:
                    raise ValidationError("Cette proposition a déjà été traitée.")
                action = request.POST.get("action")
                if action == "accepter":
                    edition, _, _ = importer_source(proposition.document, ecole=ecole)
                    proposition.etat = PropositionReferentiel.ACCEPTEE
                    if edition not in choix_bases(ecole, proposition.classe.annee_scolaire).versions:
                        contexte["edition_a_autoriser"] = True
                elif action == "refuser":
                    proposition.etat = PropositionReferentiel.REFUSEE
                else:
                    raise ValidationError("Action inconnue.")
                proposition.document = ""
                proposition.save(update_fields=["etat", "document"])
            messages.success(request, proposition.get_etat_display())
            if not contexte.get("edition_a_autoriser"):
                return redirect("propositions_referentiels_ecole")
        except ValidationError as erreur:
            contexte["erreur"] = " ".join(erreur.messages)
        except IntegrityError:
            contexte["erreur"] = "Le catalogue a changé. Examinez de nouveau la proposition."
    contexte["proposition"] = proposition
    if proposition.document:
        contexte.update(apercu_document(proposition.document, ecole))
    return render(request, "suivi/propositions_referentiels.html", contexte, status=400 if "erreur" in contexte else 200)
