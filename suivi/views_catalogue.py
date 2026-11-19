from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, MODIFIER_ETAT, VOIR_SUIVI, autorise, charger_classe_autorisee
from .catalogue_competences import catalogue_classe, cle_libelle
from .contexte_ecole import ecole_courante
from .models import AdaptationCompetence
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante, contenu_origine
from .services.adaptations_referentiels import ajouter_au_suivi
from .views import acces_requis


@acces_requis
@require_http_methods(["GET", "HEAD", "POST"])
def catalogue(request, pk):
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole_courante(request))
    if request.method == "POST":
        if request.POST.get("action") != "ajouter_au_suivi":
            raise PermissionDenied
        try:
            ajouter_au_suivi(utilisateur=request.user, classe=classe,
                competence_id=int(request.POST.get("competence", "")),
                adoption_attendue=int(request.POST.get("adoption", "")),
                revision_attendue=int(request.POST.get("revision", "")))
        except ValueError:
            messages.error(request, "Rechargez le catalogue avant d’ajouter cette compétence.")
        except ValidationError as cause:
            messages.error(request, " ".join(cause.messages))
        else:
            messages.success(request, "Compétence ajoutée au suivi de la classe.")
        filtres = {cle: request.GET[cle][:300] for cle in ("q", "niveau", "domaine", "portee", "ajouter")
                   if request.GET.get(cle)}
        return redirect(lien("catalogue_competences", classe.pk, **filtres))
    lignes = catalogue_classe(classe, request.user)
    q = request.GET.get("q", "").strip()[:300]
    niveau = request.GET.get("niveau", "")
    domaine = request.GET.get("domaine", "")
    portee = request.GET.get("portee", "")
    domaines = list(dict.fromkeys(ligne["domaine"] for ligne in lignes))
    adoption = adoption_courante(classe)
    ouvert = bool(adoption and not adoption.clos)
    gerer = autorise(request.user, GERER_REFERENTIEL_CLASSE, classe)
    cibler = autorise(request.user, MODIFIER_ETAT, classe)
    ids_ajoutables = {c["id"] for c in contenu_origine(adoption).get("competences", [])} if ouvert and gerer else set()
    revisions = dict(AdaptationCompetence.objects.filter(classe=classe,
        annee_scolaire=classe.annee_scolaire, competence_id__in=ids_ajoutables)
        .values_list("competence_id", "revision"))
    for ligne in lignes:
        competence = ligne["competence"]
        if competence.pk in ids_ajoutables and not competence.active:
            ligne["ajout_au_suivi"] = True
            ligne["revision"] = revisions.get(competence.pk, 0)
        locale = ligne["locale"]
        if ouvert and gerer and not ligne["disponible"]:
            if locale:
                ligne["modifier"] = lien("ajout_classe", classe.pk, locale.pk, origine="catalogue")
            else:
                ligne["modifier"] = lien("adaptation_competence_classe", classe.pk, ligne["competence"].pk)
    return render(request, "suivi/catalogue_competences.html", {
        "classe": classe, "adoption": adoption, "ariane": chemin_classe(classe), "domaines": domaines,
        "q": q, "niveau": niveau, "domaine": domaine, "portee": portee,
        "ajouter": ouvert and (gerer or cibler) and request.GET.get("ajouter") == "1",
        "peut_ajouter": ouvert and (gerer or cibler),
        "creation_classe": ouvert and gerer, "creation_ciblee": ouvert and cibler,
        "lignes": [l for l in lignes if (not q or cle_libelle(q) in cle_libelle(l["competence"].libelle))
                   and (not niveau or l["competence"].niveau == niveau)
                   and (not domaine or l["domaine"] == domaine)
                   and (not portee or l["portee"] == portee)],
    })
