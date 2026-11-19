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
from .catalogue_competences import doublons_classe
from .contexte_ecole import ecole_courante
from .forms_referentiels import AjoutCompetenceForm, AdaptationCompetenceForm, ClassementCompetenceForm
from .models import AdaptationCompetence, CompetenceLocale, annee_scolaire_pour
from .navigation import chemin_retour_competences, filtre_competences, lien, retour_catalogue_ajout
from .ajouts_referentiels import definition_effective_ajout
from .adaptations_referentiels import contenu_adapte, contenus_ecole
from .rubriques import contenu_classement
from .referentiels import adoption_courante
from .services.ajouts_referentiels import (
    catalogue_reprises, corriger_classement, creer_ajout, etat_classement,
    peut_corriger_classement, proposer_ajout, reprendre_ajout, utilisations_classement,
)
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
    contenus = [contenu_classement(adoption)] if adoption else ([] if classe else [c for _, c in contenus_ecole(ecole, annee)])
    domaines = {d["id"]: d for c in contenus for d in c.get("domaines", [])}
    sous_domaines = {d["id"]: d for c in contenus for d in c.get("sous_domaines", [])}
    choix_classement = {"domaines": domaines.values(), "sous_domaines": sous_domaines.values()}
    index_url = reverse("ajouts_classe", args=[classe.pk]) if classe else reverse("ajouts_ecole") + "?annee=" + annee
    catalogue = catalogue_reprises(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe) if classe else CompetenceLocale.objects.filter(ecole=ecole, suivi_libre=False).order_by("pk")
    if locale_pk and classe:
        from .autorisations import MODIFIER_ETAT
        from django.db.models import Q
        if autorise(request.user, MODIFIER_ETAT, classe):
            catalogue = CompetenceLocale.objects.filter(Q(pk__in=catalogue.values("pk")) |
                Q(pk=locale_pk, suivi_libre=True, ecole=ecole, disponibilites__classe=classe)).distinct()
    if adoption and adoption.clos:
        catalogue = catalogue.filter(competence_id__in=[c["id"] for c in adoption.etat_final.get("contenu", {}).get("competences", [])])
    locale = next((l for l in catalogue if l.pk == locale_pk), None) if locale_pk else None
    if locale_pk and locale is None:
        raise PermissionDenied
    retour_suivi = ""
    retour_catalogue = retour_catalogue_ajout(request, classe) if classe else ""
    if classe and locale and request.GET.get("origine") == "suivi":
        from .autorisations import VOIR_SUIVI
        if autorise(request.user, VOIR_SUIVI, classe):
            retour_suivi = lien("saisie_competence", classe.pk, locale.competence_id, filtre=filtre_competences(request))
    regle = AdaptationCompetence.objects.filter(ecole=ecole, annee_scolaire=annee,
        classe=classe, competence=locale.competence).first() if locale else None
    definition = definition_effective_ajout(locale) if locale else None
    proposee = contenu_adapte(ecole, annee, definition)["competences"][0] if locale else None
    utilisations = utilisations_classement(locale) if locale else []
    peut_corriger = bool(locale and ouvert and peut_corriger_classement(request.user, locale, classe, utilisations))
    classement = ClassementCompetenceForm(initial={"niveau": locale.competence.niveau},
        conserver_domaine=True, **choix_classement) if peut_corriger else None
    usages_visibles = utilisations if peut_corriger else []
    regle_ecole = AdaptationCompetence.objects.filter(ecole=ecole, annee_scolaire=annee,
        classe__isnull=True, competence=locale.competence).first() if locale and classe else None
    libelle_ecole = bool(regle_ecole and regle_ecole.libelle is not None)
    proposition_ecole = bool(locale and classe and locale.disponibilites.filter(
        annee_scolaire=annee, classe__isnull=True).exists())
    libelle_direct = bool(locale and classe and locale.classe_origine_id == classe.pk and not libelle_ecole and not proposition_ecole)
    visibilite_directe = bool(locale and classe and locale.classe_origine_id == classe.pk and
        not proposition_ecole and not (regle_ecole and regle_ecole.visible is not None))
    choix_garder = "Suivre le libellé de l’école" if libelle_ecole else "Garder le libellé d’origine"
    visible_effective = regle.visible if regle and regle.visible is not None else proposee["active"] if proposee else True
    choix_visibilite_garder = (f"Suivre le choix de l’école (actuellement {'montrée' if proposee and proposee['active'] else 'masquée'})"
        if proposition_ecole or (regle_ecole and regle_ecole.visible is not None) else "Garder la visibilité proposée")
    initial = {"mode_libelle": "personnel" if regle and regle.libelle is not None else "garder",
        "libelle": regle.libelle if regle and regle.libelle is not None else (proposee["libelle"] if proposee else ""),
        "visibilite": visible_effective if visibilite_directe else
            "garder" if not regle or regle.visible is None else ("montrer" if regle.visible else "masquer")}
    contexte = {"auteur": request.user.pk, "ecole": ecole.pk, "annee": annee,
        "classe": classe.pk if classe else None, "adoption": adoption.pk if adoption else None,
        "locale": locale.pk if locale else None, "revision": regle.revision if regle else 0}
    if peut_corriger:
        contexte["classement"] = etat_classement(locale.competence, utilisations)
    erreur = None
    doublons = []
    form = AdaptationCompetenceForm(initial=initial, choix_garder=choix_garder, libelle_direct=libelle_direct,
        visibilite_directe=visibilite_directe, choix_visibilite_garder=choix_visibilite_garder) if locale else AjoutCompetenceForm(**choix_classement, initial={"libelle": request.GET.get("libelle", "")[:300],
            "domaine": request.GET.get("domaine"), "sous_domaine": request.GET.get("sous_domaine"),
            "niveau": filtre_competences(request) if filtre_competences(request) != "tous" else "PS"})
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
                form = AjoutCompetenceForm(request.POST, **choix_classement)
                if form.is_valid():
                    if classe and request.POST.get("confirmer_doublon") != "1":
                        doublons = doublons_classe(classe, form.cleaned_data["libelle"], request.user)
                        if doublons:
                            raise ValidationError("Vérifiez la compétence existante avant de créer un doublon.")
                    creer_ajout(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                        adoption_attendue=contexte["adoption"], domaine_id=form.cleaned_data["domaine"],
                        libelle=form.cleaned_data["libelle"], niveau=form.cleaned_data["niveau"],
                        sous_domaine_id=form.cleaned_data["sous_domaine"])
                else:
                    raise ValidationError("Vérifiez la compétence, sa section et son domaine.")
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
            elif action == "classement" and peut_corriger:
                classement = ClassementCompetenceForm(request.POST, conserver_domaine=True, **choix_classement)
                if not classement.is_valid():
                    raise ValidationError("Vérifiez la section, le domaine et le sous-domaine.")
                corriger_classement(utilisateur=request.user, locale=locale, classe=classe, annee=annee,
                    adoption_attendue=contexte["adoption"], niveau=classement.cleaned_data["niveau"],
                    domaine_id=classement.cleaned_data["domaine"], sous_domaine_id=classement.cleaned_data["sous_domaine"],
                    etat_attendu=contexte["classement"])
                messages.success(request, "Classement corrigé. Les observations sont conservées.")
                return redirect(request.get_full_path())
            elif action == "adapter" and locale:
                form = AdaptationCompetenceForm(request.POST, choix_garder=choix_garder,
                    libelle_direct=libelle_direct, visibilite_directe=visibilite_directe,
                    choix_visibilite_garder=choix_visibilite_garder)
                if form.is_valid():
                    enregistrer_adaptation(utilisateur=request.user, ecole=ecole, annee=annee, classe=classe,
                        competence=locale.competence, adoption_attendue=contexte["adoption"],
                        revision_attendue=contexte["revision"], **{k: form.cleaned_data[k] for k in ("libelle", "visible")})
                else:
                    raise ValidationError("Vérifiez vos choix de libellé et de visibilité.")
            else:
                raise ValidationError("Choisissez une action proposée sur cette page.")
            messages.success(request, "Choix enregistré. Aucune réussite n'a été créée ou copiée.")
            return redirect(retour_suivi or retour_catalogue or index_url)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    lignes = []
    for ajout in catalogue.select_related("classe_origine", "competence__domaine", "competence__sous_domaine"):
        retenu = ajout.disponibilites.filter(classe=classe, annee_scolaire=annee).exists() if classe else False
        propose = ajout.disponibilites.filter(classe__isnull=True, annee_scolaire=annee).exists()
        disponible = retenu if classe else ajout.disponibilites.filter(annee_scolaire=annee).exists()
        effectif = contenu_adapte(ecole, annee, definition_effective_ajout(ajout), classe)["competences"][0]
        if adoption and adoption.clos:
            effectif = next((c for c in adoption.etat_final.get("contenu", {}).get("competences", [])
                             if c["id"] == ajout.competence_id), ajout.definition["competences"][0])
        url = reverse("ajout_classe", args=[classe.pk, ajout.pk]) if classe else reverse("ajout_ecole", args=[ajout.pk]) + "?annee=" + annee
        lignes.append({"locale": ajout, "definition": effectif, "retenu": retenu, "propose": propose,
                       "url": url, "adaptable": disponible})
    adaptable = bool(locale and locale.disponibilites.filter(annee_scolaire=annee,
        **({"classe": classe} if classe else {})).exists())
    lignes.sort(key=lambda ligne: ligne["definition"]["libelle"].casefold())
    courante = next((l["definition"] for l in lignes if locale and l["locale"].pk == locale.pk), None)
    origine = locale.definition["competences"][0] if locale else None
    from .autorisations import MODIFIER_ETAT
    return render(request, "suivi/ajouts_referentiels.html", {"classe": classe, "annee": annee,
        "peut_suivi_libre": bool(classe and ouvert and autorise(request.user, MODIFIER_ETAT, classe)),
        "direction": direction, "ouvert": ouvert, "doublons": doublons, "form": form, "lignes": lignes, "locale": locale,
        "origine": origine, "retour_suivi": retour_suivi, "retour_catalogue": retour_catalogue,
        "ariane": chemin_retour_competences(classe, retour_catalogue) if retour_catalogue else [], "courante": courante, "proposee": proposee, "libelle_ecole": libelle_ecole,
        "classement": classement, "usages_classement": usages_visibles,
        "visibilite_directe": visibilite_directe, "adaptable": adaptable, "index_url": index_url, "erreur": erreur,
        "jeton": None if perime else signing.dumps(contexte, salt="ajouts-referentiels")}, status=400 if erreur else 200)
