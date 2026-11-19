from django.contrib import messages
from django.core import signing
from django.db import transaction
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
from .models import AdaptationCompetence, Competence
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante, contenu_adoption, contenu_origine
from .services.adaptations_referentiels import ajouter_au_suivi
from .services.ajouts_referentiels import catalogue_reprises, reprendre_ajout
from .services.sources_catalogue import ajouter_depuis_source, competence_id_source, lignes_source, sources_catalogue
from .services.selection_catalogue import regler_selection
from .suivi_libre import est_libre
from .views import acces_requis


FILTRES = ("source", "q", "niveau", "domaine", "sous_domaine", "portee", "ajouter")
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
    retour = lien("catalogue_competences", classe.pk, **criteres_catalogue(request))
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
            return redirect(lien("saisie_competence", classe.pk, competence.pk))
        except signing.BadSignature:
            form.add_error(None, "Le formulaire a expiré. Rechargez la page.")
        except ValidationError as cause:
            form.add_error(None, cause)
    return render(request, "suivi/portee_catalogue.html", {"classe": classe, "libelle": candidat["libelle"],
                  "ariane": chemin_classe(classe), "form": form, "retour": retour})


@acces_requis
@require_http_methods(["GET", "HEAD", "POST"])
def catalogue(request, pk):
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole_courante(request))
    source = request.GET.get("source", "")[:40]
    if request.GET.get("selection"):
        return choix_portee(request, classe, source, request.GET["selection"][:120])
    if request.method == "POST":
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
        return redirect(lien("catalogue_competences", classe.pk, **criteres_catalogue(request)))
    q = request.GET.get("q", "").strip()[:300]
    niveau = request.GET.get("niveau", "")
    portee = request.GET.get("portee", "")
    adoption = adoption_courante(classe)
    ouvert = bool(adoption and not adoption.clos)
    gerer = ouvert and autorise(request.user, GERER_REFERENTIEL_CLASSE, classe)
    cibler = ouvert and autorise(request.user, MODIFIER_ETAT, classe)
    ajouter = (gerer or cibler) and request.GET.get("ajouter") == "1"
    eleve = eleve_contextuel(request, classe) if ajouter else None
    collectif = ajouter and request.GET.get("collectif") == "1"
    contenu = contenu_origine(adoption) if adoption else {}
    classement = next((d for d in contenu.get("domaines", [])
                       if str(d["id"]) == request.GET.get("classement")), {})
    groupe = next((g for g in contenu.get("sous_domaines", [])
                  if str(g["id"]) == request.GET.get("groupe") and g["domaine_id"] == classement.get("id")), {})
    domaine = request.GET.get("domaine", classement.get("nom", "") if not source else "")
    sous_domaine = request.GET.get("sous_domaine", groupe.get("nom", "") if not source else "")
    parametres = criteres_catalogue(request)
    sources = sources_catalogue(request.user, classe, adoption) if gerer else {}
    if source and source not in sources:
        raise PermissionDenied
    lignes = catalogue_classe(classe, request.user)
    if source:
        _, version, autre = sources[source]
        externes = list(lignes_source(version, autre, utilisateur=request.user, classe=classe))
        disponibles = [dict(reference=ref, competence=c, domaine=nom, sous_domaine=sous)
                       for ref, c, nom, sous in externes]
        presents = {ligne["competence"].pk: ligne for ligne in lignes if not ligne["disponible"]}
        if version and version.source.ecole_id is None:
            from .models import CompetenceSourceEcole
            ids = dict(CompetenceSourceEcole.objects.filter(ecole=classe.ecole, identite__source=version.source)
                       .values_list("identite__identifiant", "competence_id"))
        else:
            ids = {ref: c["id"] for ref, c, _, _ in externes}
        for ligne in disponibles:
            deja = presents.get(ids.get(ligne["reference"]))
            ligne["deja_suivie"] = bool(deja and deja["competence"].active)
            if ligne["deja_suivie"]:
                ligne["url"] = deja["url"]
            if cibler and (not ajouter or not ligne["deja_suivie"] or deja["portee"] == "cible"):
                ligne["choix_portee"] = lien("catalogue_competences", classe.pk,
                    **parametres, selection=ligne["reference"])
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
    revisions = dict(AdaptationCompetence.objects.filter(classe=classe,
        annee_scolaire=classe.annee_scolaire, competence_id__in=ids_ajoutables)
        .values_list("competence_id", "revision"))
    for ligne in lignes:
        competence = ligne["competence"]
        if competence.pk in ids_ajoutables and not competence.active:
            ligne["ajout_au_suivi"] = True
            ligne["revision"] = revisions.get(competence.pk, 0)
        locale = ligne["locale"]
        if gerer and cibler and not (locale and locale.suivi_libre):
            if ligne["disponible"] or not ajouter or not competence.active or ligne["portee"] == "cible":
                ligne["choix_portee"] = lien("catalogue_competences", classe.pk, **parametres, selection=competence.pk)
        if ouvert and gerer and not ligne["disponible"]:
            if locale:
                ligne["modifier"] = lien("ajout_classe", classe.pk, locale.pk, origine="catalogue")
            else:
                ligne["modifier"] = lien("adaptation_competence_classe", classe.pk, ligne["competence"].pk)
    def classement_retenu(ligne):
        return (not domaine or ligne["domaine"] == domaine) and (not sous_domaine or ligne["sous_domaine"] == sous_domaine)

    lignes = recherche_catalogue([
        l for l in lignes if classement_retenu(l) and (not niveau or l["competence"].niveau == niveau)
        and (not portee or l["portee"] == portee)], q)
    disponibles = recherche_catalogue([
        l for l in disponibles if classement_retenu(l) and (not niveau or l["competence"]["niveau"] == niveau)
    ], q, externe=True)
    # Le sous-domaine d'origine sert à la création, même après consultation d'une autre source.
    creation = {"libelle": q, "origine": "catalogue",
                "retour": lien("catalogue_competences", classe.pk, **parametres)}
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
        "classe": classe, "adoption": adoption, "ariane": chemin_classe(classe),
        "q": q, "niveau": niveau, "domaine": domaine, "portee": portee,
        "domaines": domaines, "groupes": groupes, "sous_domaine": sous_domaine,
        "source": source, "sources": sources, "nom_source": sources[source][0] if source else "",
        "disponibles": disponibles, "lignes": lignes, "nombre": len(lignes) + len(disponibles),
        "ajouter": ajouter, "peut_ajouter": gerer or cibler,
        "url_ajouter": lien("catalogue_competences", classe.pk, **{**parametres, "ajouter": 1}),
        "url_creation_classe": lien("ajouts_classe", classe.pk, filtre=niveau or "tous",
            ancre="creer", **creation) if gerer else "",
        "url_creation_ciblee": lien("ajouter_reussite", classe.pk, filtre=niveau or "tous", **creation,
            **({"eleve": eleve.pk} if eleve else {"collectif": 1} if collectif else {})) if cibler else "",
        "contexte_ajout": {cle: parametres[cle] for cle in CONTEXTE if cle in parametres},
        "eleve": eleve, "collectif": collectif,
        "url_catalogue": reverse("catalogue_competences", args=[classe.pk]),
        "url_resultats": lien("catalogue_competences", classe.pk, **parametres),
    }
    if request.GET.get("fragment") == "1":
        response = render(request, "suivi/partiels/catalogue_resultats.html", contexte)
        response.headers["X-Petits-Pas-Catalogue"] = "1"
        return response
    return render(request, "suivi/catalogue_competences.html", contexte)
