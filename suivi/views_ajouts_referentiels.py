"""Ajouter, proposer et reprendre des compétences, avec une portée explicite."""
from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE,
                           autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .forms_referentiels import AjoutCompetenceForm, AdaptationCompetenceForm
from .models import AdaptationCompetence, CompetenceLocale, annee_scolaire_pour
from .adaptations_referentiels import contenu_adapte, contenus_ecole
from .referentiels import adoption_courante, contenu_origine
from .services.ajouts_referentiels import catalogue_reprises, creer_ajout, proposer_ajout, reprendre_ajout
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.choix_bases_referentiels import verifier_annee
from .views import acces_requis


@acces_requis
@require_http_methods(["GET", "POST"])
def ajouts(request, classe_pk=None, locale_pk=None):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole) if classe_pk else None
    direction = autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole)
    if not classe and not direction:
        raise PermissionDenied
    annee = classe.annee_scolaire if classe else request.GET.get("annee", annee_scolaire_pour(timezone.localdate()))
    try:
        verifier_annee(annee)
    except ValidationError as cause:
        return render(request, "suivi/ajouts_referentiels.html", {"erreur": " ".join(cause.messages)}, status=400)
    adoption = adoption_courante(classe)
    ouvert = not classe or bool(adoption and not adoption.clos)
    contenus = [contenu_origine(adoption)] if adoption else ([] if classe else [c for _, c in contenus_ecole(ecole, annee)])
    domaines = {d["id"]: d for c in contenus for d in c.get("domaines", [])}
    index_url = reverse("ajouts_classe", args=[classe.pk]) if classe else reverse("ajouts_ecole") + "?annee=" + annee
    catalogue = catalogue_reprises(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe) if classe else CompetenceLocale.objects.filter(ecole=ecole).order_by("pk")
    if adoption and adoption.clos:
        catalogue = catalogue.filter(competence_id__in=[c["id"] for c in adoption.etat_final.get("contenu", {}).get("competences", [])])
    locale = next((l for l in catalogue if l.pk == locale_pk), None) if locale_pk else None
    if locale_pk and locale is None:
        raise PermissionDenied
    regle = AdaptationCompetence.objects.filter(ecole=ecole, annee_scolaire=annee,
        classe=classe, competence=locale.competence).first() if locale else None
    proposee = contenu_adapte(ecole, annee, locale.definition)["competences"][0] if locale and classe else (locale.definition["competences"][0] if locale else None)
    regle_ecole = AdaptationCompetence.objects.filter(ecole=ecole, annee_scolaire=annee,
        classe__isnull=True, competence=locale.competence).first() if locale and classe else None
    libelle_ecole = bool(regle_ecole and regle_ecole.libelle is not None)
    libelle_direct = bool(locale and classe and locale.classe_origine_id == classe.pk and not libelle_ecole)
    choix_garder = "Suivre le libellé de l’école" if libelle_ecole else "Garder le libellé d’origine"
    initial = {"mode_libelle": "personnel" if regle and regle.libelle is not None else "garder",
        "libelle": regle.libelle if regle and regle.libelle is not None else (proposee["libelle"] if proposee else ""), "meme_sens": False,
        "visibilite": "garder" if not regle or regle.visible is None else ("montrer" if regle.visible else "masquer")}
    contexte = {"auteur": request.user.pk, "ecole": ecole.pk, "annee": annee,
        "classe": classe.pk if classe else None, "adoption": adoption.pk if adoption else None,
        "locale": locale.pk if locale else None, "revision": regle.revision if regle else 0}
    erreur = None
    form = AdaptationCompetenceForm(initial=initial, choix_garder=choix_garder, libelle_direct=libelle_direct) if locale else AjoutCompetenceForm(domaines=domaines.values())
    perime = False
    if request.method == "POST":
        try:
            try:
                donnees = signing.loads(request.POST.get("jeton", ""), salt="ajouts-referentiels", max_age=1800)
            except signing.BadSignature as cause:
                perime = True
                raise ValidationError("Cette page a expiré. Reconsultez les ajouts avant d'enregistrer.") from cause
            if donnees != contexte:
                perime = True
                raise ValidationError("Les choix ont changé. Reconsultez les ajouts avant d'enregistrer.")
            if not ouvert:
                raise ValidationError("Choisissez une base pour une classe ouverte avant d'ajouter une compétence.")
            action = request.POST.get("action")
            if action == "creer" and locale is None:
                form = AjoutCompetenceForm(request.POST, domaines=domaines.values())
                if form.is_valid():
                    creer_ajout(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                        adoption_attendue=contexte["adoption"], domaine_id=form.cleaned_data["domaine"],
                        libelle=form.cleaned_data["libelle"], niveau=form.cleaned_data["niveau"])
                else:
                    raise ValidationError("Vérifiez l'apprentissage, sa section et son domaine.")
            elif action in ("reprendre", "proposer") and locale is None:
                try:
                    cible = catalogue.get(pk=int(request.POST.get("locale", "")))
                except (ValueError, CompetenceLocale.DoesNotExist) as cause:
                    raise PermissionDenied from cause
                if action == "reprendre" and classe:
                    reprendre_ajout(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                        locale=cible, adoption_attendue=contexte["adoption"])
                elif action == "proposer" and direction:
                    proposer_ajout(utilisateur=request.user, ecole=ecole, annee=annee, locale=cible)
                else:
                    raise PermissionDenied
            elif action == "adapter" and locale:
                form = AdaptationCompetenceForm(request.POST, choix_garder=choix_garder, libelle_direct=libelle_direct)
                if form.is_valid():
                    enregistrer_adaptation(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                        competence=locale.competence, adoption_attendue=contexte["adoption"],
                        revision_attendue=contexte["revision"], **{k: form.cleaned_data[k] for k in ("libelle", "visible", "meme_sens")})
                else:
                    raise ValidationError("Vérifiez vos choix de libellé et de visibilité.")
            else:
                raise ValidationError("Choisissez une action proposée sur cette page.")
            messages.success(request, "Choix enregistré. Aucune réussite n'a été créée ou copiée.")
            return redirect(index_url)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    lignes = []
    for ajout in catalogue.select_related("classe_origine", "competence"):
        retenu = ajout.disponibilites.filter(classe=classe, annee_scolaire=annee).exists() if classe else False
        propose = ajout.disponibilites.filter(classe__isnull=True, annee_scolaire=annee).exists()
        disponible = retenu if classe else ajout.disponibilites.filter(annee_scolaire=annee).exists()
        effectif = contenu_adapte(ecole, annee, ajout.definition, classe)["competences"][0]
        if adoption and adoption.clos:
            effectif = next((c for c in adoption.etat_final.get("contenu", {}).get("competences", [])
                             if c["id"] == ajout.competence_id), ajout.definition["competences"][0])
        url = reverse("ajout_classe", args=[classe.pk, ajout.pk]) if classe else reverse("ajout_ecole", args=[ajout.pk]) + "?annee=" + annee
        lignes.append({"locale": ajout, "definition": effectif, "retenu": retenu, "propose": propose,
                       "url": url, "adaptable": disponible})
    adaptable = bool(locale and locale.disponibilites.filter(annee_scolaire=annee,
        **({"classe": classe} if classe else {})).exists())
    courante = next((l["definition"] for l in lignes if locale and l["locale"].pk == locale.pk), None)
    origine = locale.definition["competences"][0] if locale else None
    return render(request, "suivi/ajouts_referentiels.html", {"classe": classe, "annee": annee,
        "direction": direction, "ouvert": ouvert, "form": form, "lignes": lignes, "locale": locale,
        "origine": origine, "courante": courante, "proposee": proposee, "libelle_ecole": libelle_ecole, "adaptable": adaptable, "index_url": index_url, "erreur": erreur,
        "jeton": None if perime else signing.dumps(contexte, salt="ajouts-referentiels")}, status=400 if erreur else 200)
