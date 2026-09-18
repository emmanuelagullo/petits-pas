from functools import wraps
import logging
import mimetypes
import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from collections import OrderedDict
from urllib.parse import quote, unquote

from django.contrib import messages
from django.contrib.staticfiles import finders
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import (
    Bilan,
    Classe,
    Competence,
    Domaine,
    Ecole,
    Eleve,
    Observation,
    ParametresCarnet,
    Scolarite,
    Trace,
)


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Accès
# --------------------------------------------------------------------------


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})


def acces_requis(vue):
    @wraps(vue)
    def _vue(request, *args, **kwargs):
        if not request.session.get("ecole_id"):
            request.session["suivant"] = request.get_full_path()
            return redirect("connexion")
        return vue(request, *args, **kwargs)

    return _vue


def direction_requise(vue):
    @wraps(vue)
    @acces_requis
    def _vue(request, *args, **kwargs):
        if request.session.get("role") != "direction":
            return HttpResponseForbidden(
                "Cette page est réservée au mot de passe de direction."
            )
        return vue(request, *args, **kwargs)

    return _vue


def ecole_courante(request):
    return get_object_or_404(Ecole, pk=request.session["ecole_id"])


def connexion(request):
    if request.method == "POST":
        saisi = request.POST.get("mot_de_passe", "")
        for ecole in Ecole.objects.all():
            role = ecole.verifier(saisi)
            if role:
                request.session["ecole_id"] = ecole.pk
                request.session["role"] = role
                return redirect(request.session.pop("suivant", None) or "accueil")
        messages.error(
            request, "Ce mot de passe ne correspond à aucune école. Vérifiez la casse."
        )
    return render(request, "suivi/connexion.html")


def deconnexion(request):
    request.session.flush()
    return redirect("connexion")


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------


@acces_requis
def accueil(request):
    ecole = ecole_courante(request)
    classes = ecole.classes.annotate(
        nb_eleves=Count(
            "scolarites__eleve",
            filter=Q(scolarites__eleve__archive_le__isnull=True),
            distinct=True,
        )
    )
    return render(request, "suivi/accueil.html", {"classes": classes})


FILTRES_NIVEAU_CLASSE = {"classe", "tous", "PS", "MS", "GS"}


def _progression(eleves, ecole, filtre="classe"):
    """Nombre de compétences réussies par élève, en un seul aller-retour.

    ``filtre`` vaut :
    - ``"classe"`` (par défaut) : les compétences du niveau propre à chaque
      élève (« Année de classe ») ;
    - ``"tous"`` : l'ensemble des compétences du cycle ;
    - ``"PS"``, ``"MS"`` ou ``"GS"`` : uniquement les compétences de ce niveau,
      pour tous les élèves affichés, quel que soit leur propre niveau.

    Renvoie le nombre total de compétences actives du cycle (utile pour
    l'affichage global), indépendamment du filtre appliqué par élève.
    """
    totaux_par_niveau = dict(
        Competence.objects.filter(domaine__ecole=ecole, active=True)
        .values("niveau")
        .annotate(n=Count("pk"))
        .values_list("niveau", "n")
    )
    total_cycle = sum(totaux_par_niveau.values())

    reussies_par_eleve_et_niveau = {}
    lignes = (
        Observation.objects.filter(
            eleve__pk__in=[e.pk for e in eleves], statut="reussi"
        )
        .values("eleve_id", "competence__niveau")
        .annotate(n=Count("pk"))
    )
    for ligne in lignes:
        reussies_par_eleve_et_niveau.setdefault(ligne["eleve_id"], {})[
            ligne["competence__niveau"]
        ] = ligne["n"]

    for e in eleves:
        par_niveau = reussies_par_eleve_et_niveau.get(e.pk, {})
        if filtre == "tous":
            e.nb_reussies = sum(par_niveau.values())
            e.total_competences = total_cycle
        elif filtre in {"PS", "MS", "GS"}:
            e.nb_reussies = par_niveau.get(filtre, 0)
            e.total_competences = totaux_par_niveau.get(filtre, 0)
        else:  # "classe" : le niveau propre à l'élève
            e.nb_reussies = par_niveau.get(e.niveau, 0)
            e.total_competences = totaux_par_niveau.get(e.niveau, 0)
        e.part_reussies = (
            round(100 * e.nb_reussies / e.total_competences)
            if e.total_competences
            else 0
        )
    return total_cycle


def _bilans_par_eleve(eleves, classe):
    """Nombre de bilans déjà déposés, pour la scolarité de chacun dans cette classe."""
    compte = dict(
        Bilan.objects.filter(scolarite__classe=classe, scolarite__eleve__in=eleves)
        .values("scolarite__eleve_id")
        .annotate(n=Count("pk"))
        .values_list("scolarite__eleve_id", "n")
    )
    for e in eleves:
        e.nb_bilans = compte.get(e.pk, 0)


@acces_requis
def classe_detail(request, pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    eleves = list(classe.eleves)
    filtre = request.GET.get("niveaux", "classe")
    if filtre not in FILTRES_NIVEAU_CLASSE:
        filtre = "classe"
    total = _progression(eleves, ecole, filtre)
    _bilans_par_eleve(eleves, classe)
    return render(
        request,
        "suivi/classe.html",
        {
            "classe": classe,
            "eleves": eleves,
            "total_competences": total,
            "filtre": filtre,
        },
    )


# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------


def _arbre(ecole, niveaux=None):
    competences = Competence.objects.filter(active=True).select_related("sous_domaine")
    if niveaux:
        competences = competences.filter(niveau__in=niveaux)
    return Domaine.objects.filter(ecole=ecole).prefetch_related(
        Prefetch("competences", queryset=competences, to_attr="visibles"),
        "attendus",
    )


@acces_requis
def saisie_eleve(request, pk):
    """L'écran du quotidien : un enfant, tout ce qu'il sait faire."""
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole, archive_le__isnull=True)
    filtre = request.GET.get("niveaux", "tous")
    niveaux = None if filtre == "tous" else [filtre]

    etats = {
        o.competence_id: o for o in eleve.observations.prefetch_related("traces")
    }
    domaines = []
    for d in _arbre(ecole, niveaux):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles]
        if lignes:
            domaines.append((d, lignes))

    return render(
        request,
        "suivi/saisie_eleve.html",
        {"eleve": eleve, "domaines": domaines, "filtre": filtre},
    )


@acces_requis
def choisir_competence(request, pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    domaines = [(d, d.visibles) for d in _arbre(ecole) if d.visibles]
    return render(
        request,
        "suivi/choisir_competence.html",
        {"classe": classe, "domaines": domaines},
    )


@acces_requis
def saisie_competence(request, pk, competence_pk):
    """La saisie éclair : une compétence, toute la classe d'un coup."""
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    etats = {
        o.eleve_id: o
        for o in Observation.objects.filter(
            competence=competence, eleve__scolarites__classe=classe
        ).prefetch_related("traces")
    }
    lignes = [(e, etats.get(e.pk)) for e in classe.eleves]
    return render(
        request,
        "suivi/saisie_competence.html",
        {"classe": classe, "competence": competence, "lignes": lignes},
    )


def _contexte_grille_competence(request, pk, competence_pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    competence = get_object_or_404(
        Competence, pk=competence_pk, domaine__ecole=ecole
    )
    etats = {
        observation.eleve_id: observation
        for observation in Observation.objects.filter(
            competence=competence,
            eleve__scolarites__classe=classe,
        )
    }
    lignes = []
    compteurs = {"a_observer": 0, "en_cours": 0, "reussi": 0}
    for eleve in classe.eleves:
        observation = etats.get(eleve.pk)
        if observation and observation.statut == Observation.REUSSI:
            etat = "reussi"
        elif observation and observation.statut == Observation.EN_COURS:
            etat = "en_cours"
        else:
            etat = "a_observer"
        compteurs[etat] += 1
        lignes.append((eleve, observation, etat))
    return {
        "classe": classe,
        "competence": competence,
        "lignes": lignes,
        "compteurs": compteurs,
        "edite_le": timezone.localdate(),
    }


@acces_requis
@require_safe
def grille_competence(request, pk, competence_pk):
    return render(
        request,
        "suivi/grille_competence.html",
        _contexte_grille_competence(request, pk, competence_pk),
    )


@never_cache
@acces_requis
@require_safe
def grille_competence_pdf(request, pk, competence_pk):
    contexte = _contexte_grille_competence(request, pk, competence_pk)
    html = render_to_string(
        "suivi/grille_competence.html",
        {**contexte, "generation_pdf": True},
        request=request,
    )
    feuille_style = finders.find("suivi/carnet.css")
    if not feuille_style:
        raise RuntimeError("La feuille de style est introuvable.")
    contenu = _generer_pdf(
        html,
        request.build_absolute_uri("/"),
        feuille_style,
    )
    nom_classe = slugify(contexte["classe"].nom) or "classe"
    nom_competence = slugify(contexte["competence"].code) or "competence"
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = (
        f'attachment; filename="grille-{nom_classe}-{nom_competence}.pdf"'
    )
    return reponse


SUITE = {
    None: Observation.REUSSI,
    Observation.REUSSI: Observation.EN_COURS,
    Observation.EN_COURS: Observation.NON_DEBUTE,
    Observation.NON_DEBUTE: Observation.REUSSI,
}


@acces_requis
def basculer(request, eleve_pk, competence_pk):
    """Un clic fait avancer l'état : rien → réussi → en cours → rien."""
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=eleve_pk, ecole=ecole, archive_le__isnull=True)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)

    obs = Observation.objects.filter(
        eleve=eleve,
        competence=competence,
    ).first()

    suivant = SUITE[obs.statut if obs else None]

    if obs is None:
        obs = Observation.objects.create(
            eleve=eleve,
            competence=competence,
            statut=suivant,
        )
    else:
        obs.statut = suivant
        obs.date_observation = timezone.localdate()
        obs.save(update_fields=["statut", "date_observation", "modifie_le"])

    gabarit = (
        "suivi/partiels/case_eleve.html"
        if request.GET.get("vue") == "classe"
        else "suivi/partiels/case_competence.html"
    )
    return render(
        request,
        gabarit,
        {"eleve": eleve, "competence": competence, "obs": obs},
    )


@acces_requis
def trace(request, eleve_pk, competence_pk):
    return _editer_trace(request, eleve_pk, competence_pk)


@acces_requis
def modifier_trace(request, eleve_pk, competence_pk, trace_pk):
    return _editer_trace(request, eleve_pk, competence_pk, trace_pk)


def _supprimer_media_apres_validation(nom):
    if not nom:
        return

    def supprimer():
        try:
            default_storage.delete(nom)
        except Exception:
            # Une référence orpheline est préférable à une trace pointant vers
            # un objet déjà effacé. Le nettoyage pourra alors être repris.
            logger.exception("Impossible de supprimer le média privé %r", nom)

    transaction.on_commit(supprimer)


@acces_requis
def supprimer_trace(request, eleve_pk, competence_pk, trace_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    trace_obj = get_object_or_404(
        Trace,
        pk=trace_pk,
        observation__eleve_id=eleve_pk,
        observation__competence_id=competence_pk,
        observation__eleve__ecole=ecole,
    )
    nom_photo = trace_obj.photo.name if trace_obj.photo else ""
    with transaction.atomic():
        trace_obj.delete()
        _supprimer_media_apres_validation(nom_photo)
    messages.success(request, "Trace supprimée.")
    return redirect("trace", eleve_pk=eleve_pk, competence_pk=competence_pk)


@acces_requis
def basculer_visibilite_trace(request, eleve_pk, competence_pk, trace_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    trace_obj = get_object_or_404(
        Trace,
        pk=trace_pk,
        observation__eleve_id=eleve_pk,
        observation__competence_id=competence_pk,
        observation__eleve__ecole=ecole,
    )
    trace_obj.visible_carnet = not trace_obj.visible_carnet
    trace_obj.save(update_fields=["visible_carnet", "modifie_le"])
    etat = "affichée dans le carnet" if trace_obj.visible_carnet else "masquée du carnet"
    messages.success(request, f"Trace {etat}.")
    return redirect("trace", eleve_pk=eleve_pk, competence_pk=competence_pk)


def _editer_trace(request, eleve_pk, competence_pk, trace_pk=None):
    """Ajouter ou modifier une trace datée sans écraser les précédentes."""
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=eleve_pk, ecole=ecole, archive_le__isnull=True)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    obs, _ = Observation.objects.get_or_create(eleve=eleve, competence=competence)
    trace_obj = None
    if trace_pk is not None:
        trace_obj = get_object_or_404(Trace, pk=trace_pk, observation=obs)

    if request.method == "POST":
        scolarite = eleve.scolarite_courante()
        if scolarite is None:
            return HttpResponseForbidden("Aucune scolarité n'est associée à cet élève.")
        trace_obj = trace_obj or Trace(observation=obs, scolarite=scolarite)
        ancien_nom_photo = trace_obj.photo.name if trace_obj.pk and trace_obj.photo else ""
        trace_obj.commentaire = request.POST.get("commentaire", "").strip()
        if request.POST.get("retirer_photo"):
            trace_obj.photo = None
        if request.FILES.get("photo"):
            trace_obj.photo = request.FILES["photo"]
        date = request.POST.get("date_observation")
        if date:
            trace_obj.date_observation = date
        trace_obj.visible_carnet = request.POST.get("visible_carnet") == "on"
        with transaction.atomic():
            trace_obj.save()
            nouveau_nom_photo = trace_obj.photo.name if trace_obj.photo else ""
            if ancien_nom_photo and ancien_nom_photo != nouveau_nom_photo:
                _supprimer_media_apres_validation(ancien_nom_photo)
        messages.success(request, f"Trace enregistrée pour {eleve.prenom}.")
        return redirect("trace", eleve_pk=eleve.pk, competence_pk=competence.pk)

    return render(
        request,
        "suivi/trace.html",
        {
            "eleve": eleve,
            "competence": competence,
            "obs": obs,
            "trace_obj": trace_obj,
            "traces": obs.traces.select_related("scolarite"),
            "formulations": [
                formulation.texte.replace("{prenom}", eleve.prenom).replace(
                    "<prenom>", eleve.prenom
                )
                for formulation in competence.formulations.filter(active=True)
            ],
            "date_defaut": timezone.localdate(),
        },
    )


# --------------------------------------------------------------------------
# Carnet
# --------------------------------------------------------------------------


def _contexte_carnet(request, pk, options=None):
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole)
    parametres, _ = ParametresCarnet.objects.get_or_create(ecole=ecole)
    options = request.GET if options is None else options
    modes = {"reussites", "observes", "tout"}
    mode = options.get("contenu", parametres.contenu_par_defaut)
    colonnes = options.get("colonnes", str(parametres.colonnes_par_defaut))
    regroupement = options.get(
        "regroupement", parametres.regroupement_par_defaut
    )
    afficher_attendus = options.get(
        "attendus", "1" if parametres.afficher_attendus else "0"
    ) == "1"
    afficher_sous_domaines = options.get(
        "sous_domaines", "1" if parametres.afficher_sous_domaines else "0"
    ) == "1"
    inclure_bilans = options.get(
        "bilans", "1" if parametres.inclure_bilans else "0"
    ) == "1"
    # Compatibilité avec les liens de la version 0.2.
    if options.get("tout") == "1":
        mode = "tout"
    if mode not in modes:
        mode = "observes"
    if colonnes not in {"1", "2"}:
        colonnes = "2"
    if regroupement not in {"aucun", "annuel", "mensuel", "bilan"}:
        regroupement = "aucun"

    etats = {
        o.competence_id: o
        for o in eleve.observations.select_related("competence").prefetch_related(
            "traces"
        )
    }
    for observation in etats.values():
        observation.traces_carnet = [
            trace for trace in observation.traces.all() if trace.visible_carnet
        ]
    domaines = []
    for d in _arbre(ecole):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles]
        if mode == "reussites":
            lignes = [
                (c, o) for c, o in lignes if o and o.statut == Observation.REUSSI
            ]
        elif mode == "observes":
            lignes = [
                (c, o)
                for c, o in lignes
                if o and o.statut in (Observation.REUSSI, Observation.EN_COURS)
            ]
        if lignes:
            domaines.append((d, _regrouper_lignes(eleve, lignes, regroupement)))

    scolarite = eleve.scolarite_courante()
    bilans = (
        Bilan.objects.filter(
            scolarite__eleve=eleve, visible_carnet=True
        ).select_related("scolarite")
        if inclure_bilans
        else Bilan.objects.none()
    )

    return {
        "eleve": eleve,
        "domaines": domaines,
        "mode": mode,
        "colonnes": colonnes,
        "regroupement": regroupement,
        "scolarite": scolarite,
        "bilans": bilans,
        "parametres_carnet": parametres,
        "afficher_attendus": afficher_attendus,
        "afficher_sous_domaines": afficher_sous_domaines,
        "inclure_bilans": inclure_bilans,
        "edite_le": timezone.localdate(),
    }


def _annee_scolaire_date(date):
    debut = date.year if date.month >= 8 else date.year - 1
    return f"{debut}-{debut + 1}"


def _regrouper_lignes(eleve, lignes, regroupement):
    if regroupement == "aucun":
        return [(None, lignes)]

    bilans = list(
        Bilan.objects.filter(scolarite__eleve=eleve)
        .select_related("scolarite")
        .order_by("date_bilan")
    )
    groupes = OrderedDict()
    for competence, observation in lignes:
        if observation is None:
            titre = "À découvrir"
        elif regroupement == "mensuel":
            titre = date_format(observation.date_observation, "F Y").capitalize()
        elif regroupement == "annuel":
            annee = _annee_scolaire_date(observation.date_observation)
            scolarite = eleve.scolarites.filter(annee_scolaire=annee).first()
            titre = (
                f"{scolarite.get_niveau_display()} — {annee}"
                if scolarite
                else f"Année scolaire {annee}"
            )
        else:
            bilan = next(
                (b for b in bilans if b.date_bilan >= observation.date_observation),
                None,
            )
            if bilan:
                titre = "Mes acquisitions — " + date_format(
                    bilan.date_bilan, "F Y"
                ).lower()
            elif bilans:
                titre = "Acquisitions depuis le dernier bilan"
            else:
                titre = "Premières acquisitions de l'année"
        groupes.setdefault(titre, []).append((competence, observation))
    return list(groupes.items())


SCHEMA_MEDIA_PDF = "petits-pas-media:"


def _url_media_pdf(nom):
    return SCHEMA_MEDIA_PDF + quote(nom, safe="")


def _recuperateur_pdf(noms_media):
    from weasyprint import default_url_fetcher

    noms_autorises = set(noms_media)

    def recuperer(url):
        if not url.startswith(SCHEMA_MEDIA_PDF):
            return default_url_fetcher(url)

        nom = unquote(url.removeprefix(SCHEMA_MEDIA_PDF))
        if nom not in noms_autorises:
            raise ValueError("Média non autorisé dans ce carnet.")

        return {
            "file_obj": default_storage.open(nom, "rb"),
            "mime_type": mimetypes.guess_type(nom)[0],
            "redirected_url": url,
        }

    return recuperer


def _generer_pdf(html, base_url, feuille_style, noms_media=()):
    # Le chargement tardif laisse les autres pages disponibles sur un ancien
    # environnement de démonstration qui ne fournirait pas encore Pango.
    from weasyprint import CSS, HTML

    return HTML(
        string=html,
        base_url=base_url,
        media_type="print",
        url_fetcher=_recuperateur_pdf(noms_media),
    ).write_pdf(stylesheets=[CSS(filename=feuille_style)])


@acces_requis
def carnet(request, pk):
    return render(
        request,
        "suivi/carnet.html",
        _contexte_carnet(request, pk),
    )


@never_cache
@acces_requis
@require_safe
def carnet_pdf(request, pk):
    contenu, nom = _contenu_pdf_carnet(request, pk)
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


def _contenu_pdf_carnet(request, pk, options=None):
    contexte = _contexte_carnet(request, pk, options)
    noms_media = []
    for _domaine, groupes in contexte["domaines"]:
        for _titre, lignes in groupes:
            for _competence, observation in lignes:
                if observation:
                    for trace_obj in observation.traces_carnet:
                        if trace_obj.photo:
                            trace_obj.url_photo_pdf = _url_media_pdf(trace_obj.photo.name)
                            noms_media.append(trace_obj.photo.name)
    html = render_to_string(
        "suivi/carnet.html",
        {**contexte, "generation_pdf": True},
        request=request,
    )
    feuille_style = finders.find("suivi/carnet.css")
    if not feuille_style:
        raise RuntimeError("La feuille de style du carnet est introuvable.")

    contenu = _generer_pdf(
        html,
        request.build_absolute_uri("/"),
        feuille_style,
        noms_media,
    )

    nom = slugify(contexte["eleve"].nom_court) or "eleve"
    return contenu, f"carnet-{nom}.pdf"


@never_cache
@acces_requis
def preparer_edition(request, pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    eleves = list(classe.eleves)
    parametres, _ = ParametresCarnet.objects.get_or_create(ecole=ecole)

    if request.method == "POST":
        ids = request.POST.getlist("eleves")
        selection = list(classe.eleves.filter(pk__in=ids))
        if not selection:
            messages.error(request, "Sélectionnez au moins un enfant.")
        else:
            options = {
                "contenu": request.POST.get("contenu", "observes"),
                "colonnes": request.POST.get("colonnes", "2"),
                "regroupement": request.POST.get("regroupement", "aucun"),
                "attendus": "1" if "attendus" in request.POST else "0",
                "sous_domaines": "1" if "sous_domaines" in request.POST else "0",
                "bilans": "1" if "bilans" in request.POST else "0",
            }
            archive = BytesIO()
            noms_utilises = set()
            with ZipFile(archive, "w", ZIP_DEFLATED) as fichiers:
                for eleve in selection:
                    contenu, nom = _contenu_pdf_carnet(request, eleve.pk, options)
                    base, extension = nom.rsplit(".", 1)
                    candidat = nom
                    numero = 2
                    while candidat in noms_utilises:
                        candidat = f"{base}-{numero}.{extension}"
                        numero += 1
                    noms_utilises.add(candidat)
                    fichiers.writestr(candidat, contenu)
            nom_classe = slugify(classe.nom) or "classe"
            reponse = HttpResponse(
                archive.getvalue(), content_type="application/zip"
            )
            reponse["Content-Disposition"] = (
                f'attachment; filename="carnets-{nom_classe}.zip"'
            )
            return reponse

    return render(
        request,
        "suivi/preparer_edition.html",
        {
            "classe": classe,
            "eleves": eleves,
            "parametres_carnet": parametres,
        },
    )


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------


def _message_scolarite_courante(eleve):
    """Décrit où un élève est actuellement scolarisé, pour les messages de
    confirmation après réactivation."""
    scolarite = eleve.scolarite_courante()
    if scolarite:
        return (
            f"{scolarite.classe} ({scolarite.get_niveau_display()} — "
            f"{scolarite.annee_scolaire})"
        )
    return None


def _annees_disponibles(ecole):
    return sorted(
        set(ecole.classes.values_list("annee_scolaire", flat=True)), reverse=True
    )


def _annee_courante_probable(ecole, annees):
    """La meilleure année par défaut pour l'annuaire : celle qui compte le
    plus de scolarités actives, pas nécessairement la plus récente (une
    classe de rentrée peut déjà exister, encore vide, pour l'année suivante)."""
    if not annees:
        return ""
    compte = dict(
        Scolarite.objects.filter(
            eleve__ecole=ecole, eleve__archive_le__isnull=True
        )
        .values("annee_scolaire")
        .annotate(n=Count("pk"))
        .values_list("annee_scolaire", "n")
    )
    if compte:
        return max(compte, key=lambda annee: (compte.get(annee, 0), annee))
    return annees[0]


@direction_requise
def annuaire_eleves(request):
    """Liste filtrable de tous les élèves de l'école, avec leur scolarité
    pour l'année choisie, afin de rendre déplacements et réactivations
    visibles sans passer par une classe en particulier."""
    ecole = ecole_courante(request)
    annees = _annees_disponibles(ecole)
    annee = request.GET.get("annee") or _annee_courante_probable(ecole, annees)
    niveau = request.GET.get("niveau", "tous")
    if niveau not in {"tous", "PS", "MS", "GS"}:
        niveau = "tous"
    etat = request.GET.get("etat", "actifs")
    if etat not in {"actifs", "archives", "tous"}:
        etat = "actifs"

    eleves = ecole.eleves.all()
    if etat == "actifs":
        eleves = eleves.filter(archive_le__isnull=True)
    elif etat == "archives":
        eleves = eleves.filter(archive_le__isnull=False)

    if annee:
        eleves = eleves.prefetch_related(
            Prefetch(
                "scolarites",
                queryset=Scolarite.objects.filter(
                    annee_scolaire=annee
                ).select_related("classe"),
                to_attr="scolarites_annee",
            )
        )

    resultats = []
    for eleve in eleves:
        scolarite = None
        if annee:
            scolarites_annee = getattr(eleve, "scolarites_annee", [])
            scolarite = scolarites_annee[0] if scolarites_annee else None
            if niveau != "tous" and (not scolarite or scolarite.niveau != niveau):
                continue
        eleve.scolarite_annee = scolarite
        resultats.append(eleve)
    resultats.sort(key=lambda e: (e.prenom.lower(), e.nom.lower()))

    return render(
        request,
        "suivi/annuaire.html",
        {
            "eleves": resultats,
            "annees": annees,
            "annee": annee,
            "niveau": niveau,
            "etat": etat,
        },
    )


@direction_requise
def gestion(request):
    ecole = ecole_courante(request)
    classes = ecole.classes.annotate(
        nb_eleves=Count(
            "scolarites__eleve",
            filter=Q(scolarites__eleve__archive_le__isnull=True),
            distinct=True,
        )
    )
    eleves_archives = ecole.eleves.filter(archive_le__isnull=False)
    nb_competences = Competence.objects.filter(
        domaine__ecole=ecole, active=True
    ).count()
    return render(
        request,
        "suivi/gestion.html",
        {
            "classes": classes,
            "nb_competences": nb_competences,
            "eleves_archives": eleves_archives,
        },
    )


@direction_requise
def parametres_carnet(request):
    ecole = ecole_courante(request)
    parametres, _ = ParametresCarnet.objects.get_or_create(ecole=ecole)
    if request.method == "POST":
        contenu = request.POST.get("contenu_par_defaut")
        regroupement = request.POST.get("regroupement_par_defaut")
        colonnes = request.POST.get("colonnes_par_defaut")
        if contenu in {"reussites", "observes", "tout"}:
            parametres.contenu_par_defaut = contenu
        if regroupement in {"aucun", "annuel", "mensuel", "bilan"}:
            parametres.regroupement_par_defaut = regroupement
        if colonnes in {"1", "2"}:
            parametres.colonnes_par_defaut = int(colonnes)
        parametres.titre_couverture = (
            request.POST.get("titre_couverture", "").strip()
            or "Carnet de suivi des apprentissages"
        )
        parametres.texte_couverture = request.POST.get(
            "texte_couverture", ""
        ).strip()
        parametres.afficher_attendus = "afficher_attendus" in request.POST
        parametres.afficher_sous_domaines = "afficher_sous_domaines" in request.POST
        parametres.inclure_bilans = "inclure_bilans" in request.POST
        parametres.save()
        messages.success(request, "Paramètres habituels du carnet enregistrés.")
        return redirect("parametres_carnet")
    return render(
        request,
        "suivi/parametres_carnet.html",
        {"parametres": parametres},
    )


@direction_requise
def creer_classe(request):
    ecole = ecole_courante(request)
    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        annee_scolaire = request.POST.get("annee_scolaire", "").strip()
        correspondance = re.fullmatch(r"(\d{4})-(\d{4})", annee_scolaire)
        annee_valide = (
            correspondance
            and int(correspondance.group(2)) == int(correspondance.group(1)) + 1
        )
        if nom and annee_valide:
            classe, creee = Classe.objects.get_or_create(
                ecole=ecole,
                nom=nom,
                annee_scolaire=annee_scolaire,
            )
            if not creee:
                messages.error(request, "Cette classe existe déjà pour cette année.")
                return render(request, "suivi/creer_classe.html")
            return redirect("importer_eleves", pk=classe.pk)
        messages.error(
            request,
            "Donnez un nom et une année scolaire au format 2027-2028.",
        )
    return render(request, "suivi/creer_classe.html")


@direction_requise
def parcours_eleve(request, pk):
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole)
    if request.method == "POST" and request.POST.get("action") == "reactiver":
        eleve.archive_le = None
        eleve.save(update_fields=["archive_le"])
        ou = _message_scolarite_courante(eleve)
        if ou:
            messages.success(request, f"{eleve.prenom} est de nouveau actif, dans {ou}.")
        else:
            messages.success(
                request,
                f"{eleve.prenom} est de nouveau actif, mais n'a pas encore de "
                "scolarité pour l'année en cours : ajoutez-en une ci-dessous.",
            )
        return redirect("parcours_eleve", pk=eleve.pk)

    if request.method == "POST" and request.POST.get("action") == "identite":
        prenom = request.POST.get("prenom", "").strip()
        if not prenom:
            messages.error(request, "Le prénom est obligatoire.")
        else:
            annee = request.POST.get("annee_naissance", "").strip()
            eleve.prenom = prenom
            eleve.nom = request.POST.get("nom", "").strip()
            eleve.annee_naissance = int(annee) if annee.isdigit() else None
            eleve.save(update_fields=["prenom", "nom", "annee_naissance"])
            messages.success(request, "Identité de l'élève enregistrée.")
            return redirect("parcours_eleve", pk=eleve.pk)

    if request.method == "POST" and request.POST.get("action") == "scolarite":
        classe = get_object_or_404(
            Classe,
            pk=request.POST.get("classe"),
            ecole=ecole,
        )
        niveau = request.POST.get("niveau")
        if niveau not in {"PS", "MS", "GS"}:
            messages.error(request, "Choisissez un niveau valide.")
        else:
            Scolarite.objects.update_or_create(
                eleve=eleve,
                annee_scolaire=classe.annee_scolaire,
                defaults={"classe": classe, "niveau": niveau},
            )
            messages.success(
                request,
                f"Scolarité {classe.annee_scolaire} enregistrée sans modifier les années précédentes.",
            )
            return redirect("parcours_eleve", pk=eleve.pk)

    return render(
        request,
        "suivi/parcours_eleve.html",
        {
            "eleve": eleve,
            "classes": ecole.classes.all(),
            "scolarites": eleve.scolarites.select_related("classe"),
        },
    )


@direction_requise
def importer_eleves(request, pk):
    """Coller la liste de la classe, un enfant par ligne."""
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)

    if request.method == "POST" and request.POST.get("action") == "affecter_existant":
        eleve = get_object_or_404(
            Eleve, pk=request.POST.get("eleve"), ecole=ecole
        )
        niveau = request.POST.get("niveau")
        if niveau not in {"PS", "MS", "GS"}:
            messages.error(request, "Choisissez un niveau valide.")
            return redirect("importer_eleves", pk=classe.pk)
        if eleve.archive_le and request.POST.get("reactiver") != "on":
            messages.error(
                request,
                "Confirmez la réactivation de cet élève avant de l'ajouter.",
            )
            return redirect("importer_eleves", pk=classe.pk)

        scolarite = eleve.scolarites.filter(
            annee_scolaire=classe.annee_scolaire
        ).select_related("classe").first()
        if (
            scolarite
            and scolarite.classe_id != classe.pk
            and request.POST.get("confirmer_deplacement") != "on"
        ):
            messages.error(
                request,
                f"{eleve.prenom} est déjà dans {scolarite.classe}. "
                "Confirmez explicitement son déplacement.",
            )
            return redirect("importer_eleves", pk=classe.pk)

        with transaction.atomic():
            reactive = bool(eleve.archive_le)
            if reactive:
                eleve.archive_le = None
                eleve.save(update_fields=["archive_le"])
            if scolarite:
                deja_dans_classe = scolarite.classe_id == classe.pk
                scolarite.classe = classe
                scolarite.niveau = niveau
                scolarite.save(update_fields=["classe", "niveau", "modifie_le"])
            else:
                deja_dans_classe = False
                Scolarite.objects.create(
                    eleve=eleve,
                    classe=classe,
                    annee_scolaire=classe.annee_scolaire,
                    niveau=niveau,
                )

        if deja_dans_classe and not reactive:
            messages.info(request, f"{eleve.prenom} est déjà dans {classe}.")
        else:
            messages.success(request, f"{eleve.prenom} a été ajouté à {classe}.")
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST":
        niveau_defaut = request.POST.get("niveau", "PS")
        ajoutes = 0
        for ligne in request.POST.get("liste", "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            parts = [p.strip() for p in ligne.replace("\t", ";").split(";")]
            prenom = parts[0]
            nom = parts[1] if len(parts) > 1 else ""
            niveau = (
                parts[2].upper()
                if len(parts) > 2 and parts[2].upper() in {"PS", "MS", "GS"}
                else niveau_defaut
            )
            annee_naissance = None
            if len(parts) > 3 and parts[3].isdigit():
                annee_naissance = int(parts[3])
            eleve = Eleve.objects.create(
                ecole=ecole,
                prenom=prenom,
                nom=nom,
                annee_naissance=annee_naissance,
            )
            Scolarite.objects.create(
                eleve=eleve,
                classe=classe,
                annee_scolaire=classe.annee_scolaire,
                niveau=niveau,
            )
            ajoutes += 1
        messages.success(request, f"{ajoutes} enfant(s) ajouté(s) à {classe}.")
        return redirect("classe_detail", pk=classe.pk)

    scolarites_annee = Scolarite.objects.filter(
        eleve__ecole=ecole,
        eleve__archive_le__isnull=True,
        annee_scolaire=classe.annee_scolaire,
    ).select_related("eleve", "classe")
    ids_affectes = scolarites_annee.values_list("eleve_id", flat=True)
    eleves_disponibles = ecole.eleves.filter(
        archive_le__isnull=True
    ).exclude(pk__in=ids_affectes)
    affectations_autres = scolarites_annee.exclude(classe=classe)
    eleves_archives = ecole.eleves.filter(archive_le__isnull=False)
    return render(
        request,
        "suivi/importer_eleves.html",
        {
            "classe": classe,
            "eleves_disponibles": eleves_disponibles,
            "affectations_autres": affectations_autres,
            "eleves_archives": eleves_archives,
        },
    )


@acces_requis
def bilans_eleve(request, pk):
    return _editer_bilan(request, pk)


@acces_requis
def modifier_bilan(request, pk, bilan_pk):
    return _editer_bilan(request, pk, bilan_pk)


def _editer_bilan(request, pk, bilan_pk=None):
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole)
    scolarites = eleve.scolarites.select_related("classe").order_by("-annee_scolaire")
    bilan_obj = None
    if bilan_pk is not None:
        bilan_obj = get_object_or_404(
            Bilan,
            pk=bilan_pk,
            scolarite__eleve=eleve,
        )
    if request.method == "POST":
        scolarite = get_object_or_404(
            Scolarite,
            pk=request.POST.get("scolarite"),
            eleve=eleve,
            classe__ecole=ecole,
        )
        date_bilan = request.POST.get("date_bilan")
        texte = request.POST.get("texte", "").strip()
        if date_bilan and texte:
            doublon = Bilan.objects.filter(
                scolarite=scolarite, date_bilan=date_bilan
            )
            if bilan_obj:
                doublon = doublon.exclude(pk=bilan_obj.pk)
            bilan_en_conflit = doublon.select_related("scolarite").first()
            if bilan_en_conflit:
                messages.error(
                    request,
                    "Un bilan existe déjà à cette date pour cette année scolaire. "
                    "Votre brouillon a été conservé ci-dessous, sans écraser le "
                    "bilan existant : relisez-le avant d'enregistrer.",
                )
                bilan_en_conflit.date_bilan = date_bilan
                bilan_en_conflit.texte = texte
                bilan_en_conflit.visible_carnet = (
                    request.POST.get("visible_carnet") == "on"
                )
                return render(
                    request,
                    "suivi/bilans.html",
                    {
                        "eleve": eleve,
                        "scolarites": scolarites,
                        "bilans": Bilan.objects.filter(
                            scolarite__eleve=eleve
                        ).select_related("scolarite"),
                        "bilan_obj": bilan_en_conflit,
                        "date_defaut": timezone.localdate(),
                    },
                )
            bilan_obj = bilan_obj or Bilan()
            bilan_obj.scolarite = scolarite
            bilan_obj.date_bilan = date_bilan
            bilan_obj.texte = texte
            bilan_obj.visible_carnet = request.POST.get("visible_carnet") == "on"
            bilan_obj.save()
            messages.success(request, "Quelques mots sur le parcours enregistrés.")
            return redirect("bilans_eleve", pk=eleve.pk)
        messages.error(request, "La date et le texte sont obligatoires.")
    return render(
        request,
        "suivi/bilans.html",
        {
            "eleve": eleve,
            "scolarites": scolarites,
            "bilans": Bilan.objects.filter(scolarite__eleve=eleve).select_related(
                "scolarite"
            ),
            "bilan_obj": bilan_obj,
            "date_defaut": timezone.localdate(),
        },
    )


@acces_requis
def supprimer_bilan(request, pk, bilan_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    bilan = get_object_or_404(Bilan, pk=bilan_pk, scolarite__eleve=eleve)
    bilan.delete()
    messages.success(request, "Bilan supprimé.")
    return redirect("bilans_eleve", pk=eleve.pk)


@acces_requis
def basculer_visibilite_bilan(request, pk, bilan_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    bilan = get_object_or_404(Bilan, pk=bilan_pk, scolarite__eleve=eleve)
    bilan.visible_carnet = not bilan.visible_carnet
    bilan.save(update_fields=["visible_carnet", "modifie_le"])
    etat = "affiché dans le carnet" if bilan.visible_carnet else "masqué du carnet"
    messages.success(request, f"Bilan {etat}.")
    return redirect("bilans_eleve", pk=eleve.pk)


@direction_requise
def archiver_eleve(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    eleve.archive_le = timezone.now()
    eleve.save(update_fields=["archive_le"])
    messages.success(request, f"{eleve.prenom} a été archivé sans supprimer son parcours.")
    return redirect("gestion")


@direction_requise
def desarchiver_eleve(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    eleve.archive_le = None
    eleve.save(update_fields=["archive_le"])
    ou = _message_scolarite_courante(eleve)
    if ou:
        messages.success(request, f"{eleve.prenom} est de nouveau actif, dans {ou}.")
    else:
        messages.success(
            request,
            f"{eleve.prenom} est de nouveau actif, mais n'a pas encore de "
            "scolarité pour l'année en cours : ajoutez-en une depuis son parcours.",
        )
    return redirect("gestion")
