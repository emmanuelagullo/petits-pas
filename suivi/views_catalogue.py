from django.shortcuts import render
from django.views.decorators.http import require_safe

from .autorisations import GERER_REFERENTIEL_CLASSE, MODIFIER_ETAT, VOIR_SUIVI, autorise, charger_classe_autorisee
from .catalogue_competences import catalogue_classe, cle_libelle
from .contexte_ecole import ecole_courante
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante
from .views import acces_requis


@acces_requis
@require_safe
def catalogue(request, pk):
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole_courante(request))
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
    for ligne in lignes:
        locale = ligne["locale"]
        if ouvert and gerer and not ligne["disponible"]:
            if locale:
                ligne["modifier"] = lien("ajout_classe", classe.pk, locale.pk, origine="catalogue")
            else:
                ligne["modifier"] = lien("adaptation_competence_classe", classe.pk, ligne["competence"].pk)
    return render(request, "suivi/catalogue_competences.html", {
        "classe": classe, "ariane": chemin_classe(classe), "domaines": domaines,
        "q": q, "niveau": niveau, "domaine": domaine, "portee": portee,
        "ajouter": ouvert and (gerer or cibler) and request.GET.get("ajouter") == "1",
        "peut_ajouter": ouvert and (gerer or cibler),
        "creation_classe": ouvert and gerer, "creation_ciblee": ouvert and cibler,
        "lignes": [l for l in lignes if (not q or cle_libelle(q) in cle_libelle(l["competence"].libelle))
                   and (not niveau or l["competence"].niveau == niveau)
                   and (not domaine or l["domaine"] == domaine)
                   and (not portee or l["portee"] == portee)],
    })
