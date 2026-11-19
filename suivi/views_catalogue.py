from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, MODIFIER_ETAT, VOIR_SUIVI, autorise, charger_classe_autorisee
from .catalogue_competences import catalogue_classe
from .consultation_referentiels import rechercher_apprentissages
from .contexte_ecole import ecole_courante
from .forms_suivi_libre import PorteeCatalogueForm
from .gestion_catalogue import changer_visibilite, deplacer
from .models import AdaptationCompetence, Competence
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante, contenu_adoption, contenu_origine
from .rubriques import contenu_classement, rubriques_masquees, rubriques_saisissables
from .services.adaptations_referentiels import ajouter_au_suivi
from .services.ajouts_referentiels import catalogue_reprises, reprendre_ajout
from .services.sources_catalogue import ajouter_depuis_source, competence_id_source, lignes_source, sources_catalogue
from .services.selection_catalogue import regler_selection
from .suivi_libre import est_libre
from .views import acces_requis


FILTRES = ("source", "q", "niveau", "domaine", "sous_domaine", "portee", "ajouter", "depuis_saisie", "inclure_masquees", "inclure_competences_masquees")
CONTEXTE = ("classement", "groupe", "eleve", "collectif")


def criteres_catalogue(request):
    return {cle: request.GET[cle][:300] for cle in (*FILTRES, *CONTEXTE) if cle in request.GET}


def recherche_catalogue(lignes, q, *, externe=False):
    if not q:
        return lignes
    index = [{"libelle": ligne["competence"]["libelle"] if externe else ligne["competence"].libelle, "ligne": ligne}
             for ligne in lignes]
    return [item["ligne"] for item in rechercher_apprentissages(index, q)]


def eleve_contextuel(request, classe):
    valeur = request.GET.get("eleve", "")
    if not valeur.isascii() or not valeur.isdecimal() or len(valeur) > 18:
        return None
    return classe.eleves.filter(pk=int(valeur)).first()


def choix_portee(request, classe, source, reference):
    adoption = adoption_courante(classe)
    if not adoption or adoption.clos or not autorise(request.user, MODIFIER_ETAT, classe) or not autorise(
            request.user, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    regle = reprise = None
    if source:
        choix = sources_catalogue(request.user, classe, adoption).get(source)
        if choix is None:
            raise PermissionDenied
        _, version, autre = choix
        candidat = next((c for ref, c, _, _ in lignes_source(version, autre, utilisateur=request.user, classe=classe)
                         if ref == reference), None)
        if candidat:
            cid = competence_id_source(classe, version, reference, candidat)
            regle = AdaptationCompetence.objects.filter(classe=classe, competence_id=cid).first()
    else:
        candidats = contenu_adoption(adoption).get("competences", [])
        candidat = next((c for c in candidats if str(c["id"]) == reference), None)
        if not candidat and reference.isascii() and reference.isdecimal() and len(reference) <= 18:
            reprise = catalogue_reprises(utilisateur=request.user, ecole=classe.ecole,
                annee=classe.annee_scolaire, classe=classe).filter(competence_id=int(reference)).first()
            if reprise:
                candidat = {"id": reprise.competence_id, "libelle": reprise.competence.libelle}
        if candidat:
            competence = Competence.objects.get(pk=candidat["id"])
            if est_libre(competence):
                raise PermissionDenied
            regle = AdaptationCompetence.objects.filter(classe=classe, competence=competence).first()
    if candidat is None:
        raise Http404
    ciblee = bool(regle and regle.selection_eleves)
    eleve = eleve_contextuel(request, classe)
    collectif = request.GET.get("collectif") == "1"
    initial = {"portee": "eleves" if ciblee or eleve or collectif else "classe"}
    if eleve:
        initial["eleves"] = [eleve.pk]
    elif collectif:
        initial["eleves"] = list(classe.eleves.values_list("pk", flat=True))
    if ciblee:
        deja = set(regle.eleves_selectionnes.filter(active=True, scolarite__classe=classe,
            scolarite__eleve__archive_le__isnull=True).values_list("scolarite__eleve_id", flat=True))
        initial["eleves"] = sorted(deja | set(initial.get("eleves", [])))
    attendu = [request.user.pk, classe.pk, adoption.pk, source, reference, regle.revision if regle else 0]
    initial["jeton"] = signing.dumps(attendu, salt="portee-catalogue")
    form = PorteeCatalogueForm(request.POST if request.method == "POST" else None, classe=classe, initial=initial)
    route = "choisir_competence" if request.GET.get("depuis_saisie") == "1" else "catalogue_competences"
    retour = lien(route, classe.pk, **criteres_catalogue(request))
    if request.method == "POST" and form.is_valid():
        try:
            if signing.loads(form.cleaned_data["jeton"], salt="portee-catalogue", max_age=1800) != attendu:
                raise ValidationError("Le suivi a changé. Rechargez le formulaire de sélection.")
            with transaction.atomic():
                revision = attendu[-1]
                if source:
                    competence = ajouter_depuis_source(utilisateur=request.user, classe=classe,
                        source=source, reference=reference, adoption_attendue=adoption.pk, revision_attendue=revision)
                    revision = AdaptationCompetence.objects.filter(classe=classe, competence=competence
                        ).values_list("revision", flat=True).first() or 0
                if reprise:
                    reprendre_ajout(utilisateur=request.user, ecole=classe.ecole, annee=classe.annee_scolaire,
                        classe=classe, locale=reprise, adoption_attendue=adoption.pk)
                ids = form.cleaned_data["eleves"] if form.cleaned_data["portee"] == "eleves" else None
                regler_selection(utilisateur=request.user, classe=classe, competence=competence,
                    adoption_attendue=adoption.pk, revision_attendue=revision, ids=ids)
            messages.success(request, "Le suivi de cette compétence a été mis à jour.")
            if eleve and ids is not None and eleve.pk in ids:
                return redirect(lien("saisie_eleve", eleve.pk, ancre=f"c{competence.pk}"))
            return redirect(lien("saisie_competence", classe.pk, competence.pk, retour=retour) if request.GET.get("depuis_saisie") == "1" else lien("saisie_competence", classe.pk, competence.pk))
        except signing.BadSignature:
            form.add_error(None, "Le formulaire a expiré. Rechargez la page.")
        except ValidationError as cause:
            form.add_error(None, cause)
    return render(request, "suivi/portee_catalogue.html", {"classe": classe, "libelle": candidat["libelle"],
                  "ariane": chemin_classe(classe), "form": form, "retour": retour})


@acces_requis
@require_http_methods(["GET", "HEAD", "POST"])
def catalogue(request, pk, saisie_collective=False):
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole_courante(request))
    route = "choisir_competence" if saisie_collective else "catalogue_competences"
    source = request.GET.get("source", "")[:40]
    if request.GET.get("selection"):
        return choix_portee(request, classe, source, request.GET["selection"][:120])
    retour_gestion = lien(route, classe.pk, **criteres_catalogue(request))
    deplacement = None
    if request.GET.get("deplacement"):
        deplacement = deplacer(request, classe, request.GET["deplacement"], retour_gestion)
        if not isinstance(deplacement, dict):
            return deplacement
    if request.method == "POST" and not deplacement and request.POST.get("action") == "visibilite_catalogue":
        return changer_visibilite(request, classe, retour_gestion)
    if request.method == "POST" and not deplacement:
        action = request.POST.get("action")
        if action not in ("ajouter_au_suivi", "ajouter_depuis_source"):
            raise PermissionDenied
        try:
            adoption_attendue = int(request.POST.get("adoption", ""))
            if action == "ajouter_depuis_source":
                ajouter_depuis_source(utilisateur=request.user, classe=classe, source=source,
                    reference=request.POST.get("reference", ""), adoption_attendue=adoption_attendue)
            else:
                ajouter_au_suivi(utilisateur=request.user, classe=classe,
                    competence_id=int(request.POST.get("competence", "")),
                    adoption_attendue=adoption_attendue, revision_attendue=int(request.POST.get("revision", "")))
        except ValueError:
            messages.error(request, "Rechargez le catalogue avant d’ajouter cette compétence.")
        except ValidationError as cause:
            messages.error(request, " ".join(cause.messages))
        else:
            messages.success(request, "Compétence ajoutée au suivi de la classe.")
        return redirect(lien(route, classe.pk, **criteres_catalogue(request)))
    q = request.GET.get("q", "").strip()[:300]
    niveau = request.GET.get("niveau", "") if "niveau" in request.GET else (request.GET.get("niveaux", "") if saisie_collective else "")
    niveau = niveau if niveau in {"PS", "MS", "GS"} else ""
    portee = request.GET.get("portee", "")
    adoption = adoption_courante(classe)
    ouvert = bool(adoption and not adoption.clos)
    gerer = ouvert and autorise(request.user, GERER_REFERENTIEL_CLASSE, classe)
    cibler = ouvert and autorise(request.user, MODIFIER_ETAT, classe)
    ajouter = (gerer or cibler) and (saisie_collective or request.GET.get("ajouter") == "1")
    eleve = eleve_contextuel(request, classe) if ajouter else None
    collectif = saisie_collective or (ajouter and request.GET.get("collectif") == "1")
    contenu = contenu_classement(adoption) if adoption else {}
    classement = next((d for d in contenu.get("domaines", [])
                       if str(d["id"]) == request.GET.get("classement")), {})
    groupe = next((g for g in contenu.get("sous_domaines", [])
                  if str(g["id"]) == request.GET.get("groupe") and g["domaine_id"] == classement.get("id")), {})
    domaine = request.GET.get("domaine", classement.get("nom", "") if not source else "")
    sous_domaine = request.GET.get("sous_domaine", groupe.get("nom", "") if not source else "")
    parametres = criteres_catalogue(request)
    if saisie_collective:
        parametres.update(collectif="1", ajouter="1", depuis_saisie="1")
    if niveau:
        parametres["niveau"] = niveau
    url_resultats = lien(route, classe.pk, **parametres)
    sources = sources_catalogue(request.user, classe, adoption) if gerer else {}
    if source and source not in sources:
        raise PermissionDenied
    lignes = catalogue_classe(classe, request.user)
    regles_visibilite = {
        (cid, scope): visible for cid, scope, visible in AdaptationCompetence.objects.filter(
            Q(classe=classe) | Q(classe__isnull=True), ecole=classe.ecole,
            annee_scolaire=classe.annee_scolaire, visible__isnull=False
        ).values_list("competence_id", "classe_id", "visible")
    }
    revisions_classe = dict(AdaptationCompetence.objects.filter(classe=classe)
                           .values_list("competence_id", "revision"))
    inclure_competences_masquees = request.GET.get("inclure_competences_masquees") == "1"
    deplace = next((ligne for ligne in lignes if not ligne["disponible"]
                    and str(ligne["competence"].pk) == request.GET.get("deplace")), None)
    url_deplacement = ""
    if deplace:
        choix = {cle: valeur for cle, valeur in parametres.items()
                 if cle not in ("classement", "groupe", "source", "domaine", "sous_domaine")}
        choix.update(domaine=deplace["domaine"], sous_domaine=deplace["sous_domaine"],
                     inclure_competences_masquees=1, inclure_masquees=1)
        url_deplacement = lien(route, classe.pk, **choix)
    domaines_masques, groupes_masques = rubriques_masquees(classe)
    inclure_masquees = request.GET.get("inclure_masquees") == "1"
    correspondances = bool(q and recherche_catalogue(lignes, q))
    for ligne in lignes:
        competence = ligne["competence"]
        ligne["competence_masquee"] = (not ligne["disponible"] and not competence.active
            and regles_visibilite.get((competence.pk, classe.pk), regles_visibilite.get((competence.pk, None))) is False)
        ligne["rubrique_masquee"] = competence.domaine_id in domaines_masques or competence.sous_domaine_id in groupes_masques
    a_des_competences_masquees = any(l["competence_masquee"] for l in lignes)
    presentes = {l["competence"].pk: l for l in lignes if not l["disponible"]}
    if not inclure_competences_masquees:
        lignes = [l for l in lignes if not l["competence_masquee"]]
    if not inclure_masquees:
        lignes = [ligne for ligne in lignes if not ligne["rubrique_masquee"]]
    autres_sources = []
    if q and not correspondances:
        for identifiant, (nom, version, autre) in sources.items():
            index = [{"libelle": c["libelle"]} for _, c, _, _ in
                     lignes_source(version, autre, utilisateur=request.user, classe=classe)]
            if rechercher_apprentissages(index, q):
                autres_sources.append((identifiant, nom))
        correspondances = bool(autres_sources)
    if source:
        _, version, autre = sources[source]
        externes = list(lignes_source(version, autre, utilisateur=request.user, classe=classe))
        disponibles = [dict(reference=ref, competence=c, domaine=nom, sous_domaine=sous)
                       for ref, c, nom, sous in externes]
        if version and version.source.ecole_id is None:
            from .models import CompetenceSourceEcole
            ids = dict(CompetenceSourceEcole.objects.filter(ecole=classe.ecole, identite__source=version.source)
                       .values_list("identite__identifiant", "competence_id"))
        else:
            ids = {ref: c["id"] for ref, c, _, _ in externes}
        for ligne in disponibles:
            deja = presentes.get(ids.get(ligne["reference"]))
            ligne["gestion"] = deja
            ligne["deja_suivie"] = bool(deja and deja["competence"].active)
            if ligne["deja_suivie"]:
                ligne["url"] = lien("saisie_competence", classe.pk, ids[ligne["reference"]], filtre=niveau or "tous", retour=url_resultats)
            if cibler and not (deja and deja["competence_masquee"]) and (not ajouter or not ligne["deja_suivie"] or deja["portee"] == "cible"):
                ligne["choix_portee"] = lien("catalogue_competences", classe.pk,
                    **parametres, selection=ligne["reference"])
        disponibles = [l for l in disponibles if not l["gestion"] or (
            (inclure_competences_masquees or not l["gestion"]["competence_masquee"])
            and (inclure_masquees or not l["gestion"]["rubrique_masquee"]))]
        lignes = []
    else:
        disponibles = []
    categories = disponibles if source else lignes
    domaines = sorted({l["domaine"] for l in categories} | ({classement["nom"]} if classement and not source else set()))
    if domaine not in domaines:
        domaine = ""
    groupes = sorted({l["sous_domaine"] for l in categories
                     if l["sous_domaine"] and (not domaine or l["domaine"] == domaine)}
                     | ({groupe["nom"]} if groupe and domaine == classement.get("nom") and not source else set()))
    if sous_domaine not in groupes:
        sous_domaine = ""
    ids_ajoutables = {c["id"] for c in contenu_origine(adoption).get("competences", [])} if ouvert and gerer else set()
    for ligne in presentes.values():
        competence = ligne["competence"]
        locale = ligne["locale"]
        if gerer and (not (locale and locale.suivi_libre) or cibler):
            ligne["deplacement"] = lien(route, classe.pk, **parametres, deplacement=competence.pk,
                                        ancre="deplacement-competence")
            ligne["revision_gestion"] = revisions_classe.get(competence.pk, 0)
            if ligne["competence_masquee"]:
                ligne["visibilite"] = "reafficher"
            elif competence.active:
                ligne["visibilite"] = "masquer"
            if locale:
                ligne["modifier"] = lien("ajout_classe", classe.pk, locale.pk, origine="catalogue", retour=url_resultats)
            else:
                ligne["modifier"] = lien("adaptation_competence_classe", classe.pk, competence.pk, retour=url_resultats)
    for ligne in lignes:
        competence = ligne["competence"]
        if not ligne["disponible"] and (q or domaine or sous_domaine or portee):
            ligne["url"] = lien("saisie_competence", classe.pk, competence.pk, filtre=niveau or "tous", retour=url_resultats)
        if competence.pk in ids_ajoutables and not competence.active and not ligne["competence_masquee"]:
            ligne["ajout_au_suivi"] = True
            ligne["revision"] = revisions_classe.get(competence.pk, 0)
        locale = ligne["locale"]
        if gerer and cibler and not (locale and locale.suivi_libre) and not ligne["competence_masquee"]:
            if ligne["disponible"] or not ajouter or not competence.active or ligne["portee"] == "cible":
                ligne["choix_portee"] = lien("catalogue_competences", classe.pk, **parametres, selection=competence.pk)
    def classement_retenu(ligne):
        return (not domaine or ligne["domaine"] == domaine) and (not sous_domaine or ligne["sous_domaine"] == sous_domaine)

    lignes = recherche_catalogue([
        l for l in lignes if classement_retenu(l) and (not niveau or l["competence"].niveau == niveau)
        and (not portee or l["portee"] == portee)], q)
    disponibles = recherche_catalogue([
        l for l in disponibles if classement_retenu(l) and (not niveau or l["competence"]["niveau"] == niveau)
    ], q, externe=True)
    deplacement_en_ligne = bool(deplacement and (
        any(l["competence"].pk == deplacement["competence"]["id"] for l in lignes)
        or any(l["gestion"] and l["gestion"]["competence"].pk == deplacement["competence"]["id"] for l in disponibles)
    ))
    hors_filtres = q and not (lignes or disponibles) and correspondances
    recherches_elargies = []
    if hors_filtres:
        commun = {cle: valeur for cle, valeur in parametres.items()
                  if cle not in ("niveau", "domaine", "sous_domaine", "portee", "source")}
        commun.update(niveau="", domaine="", sous_domaine="")
        if a_des_competences_masquees:
            commun["inclure_competences_masquees"] = 1
        if domaines_masques or groupes_masques:
            commun["inclure_masquees"] = 1
        recherches_elargies = [(nom, lien(route, classe.pk, **commun, source=identifiant))
                              for identifiant, nom in autres_sources]
        recherches_elargies.insert(0, ("Catalogue de la classe", lien(route, classe.pk, **commun)))
        if source and source not in dict(autres_sources):
            recherches_elargies.append((sources[source][0], lien(route, classe.pk, **commun, source=source)))
    domaines_suivi = []
    vue_suivi = saisie_collective and not (deplacement or q or source or domaine or sous_domaine or portee or inclure_masquees or inclure_competences_masquees)
    effectif = 0
    if vue_suivi:
        from .referentiels import arbre_competences
        from .statistiques import repartition_competences
        arbre = arbre_competences(classe.ecole, [niveau] if niveau else None, classe=classe)
        domaines_suivi = [(d, d.visibles) for d in rubriques_saisissables(arbre, classe)]
        effectif = repartition_competences(classe, [c for _, cs in domaines_suivi for c in cs])
    # Le sous-domaine d'origine sert à la création, même après consultation d'une autre source.
    creation = {"libelle": q, "origine": "catalogue",
                "retour": lien(route, classe.pk, **parametres)}
    if classement:
        creation["domaine"] = classement["id"]
    if groupe:
        creation["sous_domaine"] = groupe["id"]
    if not classement and not source and domaine:
        correspondance = next((d for d in contenu.get("domaines", []) if d["nom"] == domaine), None)
        if correspondance:
            creation["domaine"] = correspondance["id"]
            sous = next((g for g in contenu.get("sous_domaines", []) if g["nom"] == sous_domaine
                         and g["domaine_id"] == correspondance["id"]), None)
            if sous:
                creation["sous_domaine"] = sous["id"]
    contexte = {
        "deplacement": deplacement, "deplacement_en_ligne": deplacement_en_ligne, "url_deplacement": url_deplacement,
        "a_des_competences_masquees": a_des_competences_masquees,
        "inclure_competences_masquees": inclure_competences_masquees,
        "inclure_masquees": inclure_masquees, "rubriques_masquees": bool(domaines_masques or groupes_masques),
        "saisie_collective": saisie_collective, "vue_suivi": vue_suivi, "domaines_suivi": domaines_suivi,
        "effectif": effectif, "filtre": niveau or "tous", "responsable": cibler,
        "creer_en_priorite": bool(q and not correspondances), "recherches_elargies": recherches_elargies,
        "classe": classe, "adoption": adoption, "ariane": chemin_classe(classe),
        "q": q, "niveau": niveau, "domaine": domaine, "portee": portee,
        "domaines": domaines, "groupes": groupes, "sous_domaine": sous_domaine,
        "source": source, "sources": sources, "nom_source": sources[source][0] if source else "",
        "disponibles": disponibles, "lignes": lignes, "nombre": sum(len(cs) for _, cs in domaines_suivi) if vue_suivi else len(lignes) + len(disponibles),
        "ajouter": ajouter, "peut_ajouter": gerer or cibler,
        "url_ajouter": lien("catalogue_competences", classe.pk, **{**parametres, "ajouter": 1}),
        "url_creation_classe": lien("ajouts_classe", classe.pk, filtre=niveau or "tous",
            ancre="creer", **creation) if gerer else "",
        "url_creation_ciblee": lien("ajouter_reussite", classe.pk, filtre=niveau or "tous", **creation,
            **({"eleve": eleve.pk} if eleve else {"collectif": 1} if collectif else {})) if cibler else "",
        "contexte_ajout": {cle: parametres[cle] for cle in CONTEXTE if cle in parametres},
        "eleve": eleve, "collectif": collectif,
        "url_catalogue": reverse(route, args=[classe.pk]),
        "url_resultats": url_resultats,
    }
    if request.GET.get("fragment") == "1":
        response = render(request, "suivi/partiels/catalogue_resultats.html", contexte)
        response.headers["X-Petits-Pas-Catalogue"] = "1"
        return response
    return render(request, "suivi/choisir_competence.html" if saisie_collective else "suivi/catalogue_competences.html", contexte)
