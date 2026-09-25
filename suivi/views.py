from functools import wraps
from io import StringIO
import tempfile
import logging
import mimetypes
from pathlib import Path
import re
import shutil
from datetime import datetime
import sqlite3
from io import BytesIO
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from collections import OrderedDict
from urllib.parse import quote, unquote

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.management import call_command
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Prefetch, Q
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from comptes.models import (
    AffectationClasse,
    AppartenanceEcole,
    Invitation,
    ResponsabiliteEcole,
    Utilisateur,
)
from comptes.forms import CreationCompteInvitationForm, InstallationLocaleForm, ProfilForm

from .autorisations import (
    ACCEDER_APPLICATION,
    ADMINISTRER_ECOLE,
    CONTRIBUER,
    GENERER_CARNET,
    GERER_ELEVES_CLASSE,
    MODIFIER_ETAT,
    PREVISUALISER_CARNET,
    TELECHARGER_MEDIA_ORIGINAL,
    VOIR_CLASSE,
    VOIR_LISTE_ELEVES,
    VOIR_SUIVI,
    VOIR_MEDIA,
    VOIR_AFFECTATIONS_CLASSE,
    affectation_active,
    autorise,
    charger_classe_autorisee,
    charger_eleve_autorise,
    classes_accessibles,
    est_direction,
    peut_terminer_affectation,
)
from .audit import journaliser
from .contexte_ecole import ecole_courante
from .models import (
    AccesParcoursEleve,
    Bilan,
    Classe,
    Competence,
    DemandeRapprochementEleve,
    Domaine,
    Ecole,
    Eleve,
    Observation,
    ParametresCarnet,
    Scolarite,
    Trace,
    annee_scolaire_pour,
    bornes_annee_scolaire,
)
from .paquet_local import (
    RESULTAT,
    annuler_preparation,
    confirmer_restauration,
    creer_sauvegarde,
    lire_resultat,
    preparer_restauration,
    preparation_en_attente,
    retenir_preparation,
    restauration_en_attente,
)
from .services.eleves import (
    archiver,
    correspondances,
    desarchiver,
    importer_nouveaux_eleves,
    modifier_identite,
    modifier_niveau_courant,
    valider_rapprochement,
)
from .services.pedagogie import (
    definir_visibilite_bilan,
    definir_visibilite_trace,
    enregistrer_bilan,
    enregistrer_trace,
    modifier_etat,
    restaurer_trace,
    supprimer_bilan_logiquement,
    supprimer_trace_logiquement,
)
from .services.equipe import (
    accepter_invitation,
    activer_classe,
    attribuer_affectation,
    creer_compte_et_accepter_invitation,
    envoyer_email_invitation,
    invitation_est_utilisable,
    inviter,
    remplacer_responsable,
    revoquer_invitation,
    suspendre_affectation_urgence,
    terminer_affectation,
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
        if not request.user.is_authenticated:
            request.session["suivant"] = request.get_full_path()
            return redirect("connexion")
        ecole = ecole_courante(request)
        if ecole is None or not autorise(
            request.user, ACCEDER_APPLICATION, ecole=ecole
        ):
            return HttpResponseForbidden(
                "Ce compte ne possède aucune responsabilité active dans cette école."
            )
        return vue(request, *args, **kwargs)

    return _vue


def direction_requise(vue):
    @wraps(vue)
    @acces_requis
    def _vue(request, *args, **kwargs):
        ecole = ecole_courante(request)
        if ecole is None or not autorise(
            request.user, ADMINISTRER_ECOLE, ecole=ecole
        ):
            return HttpResponseForbidden(
                "Cette page est réservée à la direction."
            )
        return vue(request, *args, **kwargs)

    return _vue


def connexion(request):
    if settings.MODE_LOCAL and not Ecole.objects.exists() and not Utilisateur.objects.exists():
        return redirect("installation_locale")
    if request.user.is_authenticated:
        return redirect("accueil")
    if request.method == "POST":
        utilisateur = authenticate(
            request,
            username=request.POST.get("nom_utilisateur", "").strip(),
            password=request.POST.get("mot_de_passe", ""),
        )
        if utilisateur:
            login(request, utilisateur)
            ecole = ecole_courante(request)
            if ecole and autorise(
                utilisateur, ACCEDER_APPLICATION, ecole=ecole
            ):
                if (settings.MODE_LOCAL and est_direction(utilisateur, ecole)
                        and lire_resultat(Path(settings.DATABASES["default"]["NAME"]).parent)):
                    request.session.pop("suivant", None)
                    return redirect("sauvegardes_locales")
                return redirect(request.session.pop("suivant", None) or "accueil")
            logout(request)
        messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
    return render(request, "suivi/connexion.html")


@never_cache
def installation_locale(request):
    if not settings.MODE_LOCAL:
        raise Http404
    if Ecole.objects.exists():
        return redirect("accueil" if request.user.is_authenticated else "connexion")
    if Utilisateur.objects.exists():
        return HttpResponseForbidden(
            "La base contient déjà un compte. L’installation doit être vérifiée."
        )

    formulaire = InstallationLocaleForm(request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        with transaction.atomic():
            if Ecole.objects.exists() or Utilisateur.objects.exists():
                return HttpResponseForbidden("Ce paquet a déjà été initialisé.")
            ecole = Ecole.objects.create(
                nom=formulaire.cleaned_data["ecole_nom"],
                commune=formulaire.cleaned_data["commune"].strip(),
            )
            utilisateur = formulaire.save()
            appartenance = AppartenanceEcole.objects.create(
                utilisateur=utilisateur, ecole=ecole
            )
            ResponsabiliteEcole.objects.create(
                appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION
            )
            call_command(
                "charger_referentiel",
                settings.BASE_DIR / "referentiel" / "trame-cycle1.yaml",
                ecole=ecole.pk,
                stdout=StringIO(),
            )
        login(request, utilisateur, backend="django.contrib.auth.backends.ModelBackend")
        request.session["ecole_id"] = ecole.pk
        request.session.pop("suivant", None)
        messages.success(request, "École créée. Vous pouvez maintenant préparer une classe.")
        return redirect("gestion")
    return render(request, "suivi/installation_locale.html", {"formulaire": formulaire})


@never_cache
@direction_requise
def sauvegardes_locales(request):
    if not settings.MODE_LOCAL:
        raise Http404
    paquet = Path(settings.DATABASES["default"]["NAME"]).parent
    if request.method == "POST" and restauration_en_attente() is None:
        action = request.POST.get("action")
        if action == "accuser" and lire_resultat(paquet):
            (paquet / RESULTAT).unlink(missing_ok=True)
            return redirect("gestion")
        if action == "annuler":
            annuler_preparation()
            return redirect("sauvegardes_locales")
        if action == "confirmer":
            try:
                confirmer_restauration()
            except ValueError as erreur:
                messages.error(request, str(erreur))
            return redirect("sauvegardes_locales")
        if preparation_en_attente() is not None:
            return redirect("sauvegardes_locales")
        if action == "sauvegarder":
            fichier = tempfile.TemporaryFile(dir=paquet.parent)
            try:
                creer_sauvegarde(paquet, fichier)
                fichier.seek(0)
                return FileResponse(
                    fichier, as_attachment=True,
                    filename=f"petits-pas-{timezone.now():%Y%m%d-%H%M%S}.zip",
                    content_type="application/zip",
                )
            except Exception:
                fichier.close()
                raise
        if request.POST.get("action") == "restaurer":
            archive = request.FILES.get("archive")
            if not archive:
                messages.error(request, "Choisissez un fichier de sauvegarde.")
            else:
                try:
                    etape = preparer_restauration(archive, paquet.parent, paquet.name)
                    try:
                        retenir_preparation(etape)
                    except Exception:
                        shutil.rmtree(etape.etape)
                        raise
                except (ValueError, OSError, RuntimeError, KeyError, BadZipFile, sqlite3.DatabaseError) as erreur:
                    messages.error(request, f"Sauvegarde refusée : {erreur}")
                else:
                    messages.success(request, "Sauvegarde vérifiée. Vérifiez les détails avant de confirmer.")
            return redirect("sauvegardes_locales")
    preparation = restauration_en_attente() or preparation_en_attente()
    resultat = lire_resultat(paquet)
    def date_affichee(valeur):
        if not valeur:
            return "Date non indiquée (ancienne sauvegarde)"
        instant = datetime.fromisoformat(valeur)
        if timezone.is_aware(instant):
            instant = timezone.localtime(instant)
        return instant.strftime("%d/%m/%Y à %H:%M")

    return render(
        request, "suivi/sauvegardes_locales.html",
        {
            "restauration_attente": restauration_en_attente() is not None,
            "preparation": preparation,
            "paquet": paquet,
            "date_sauvegarde": date_affichee(preparation.date_sauvegarde) if preparation else None,
            "resultat": resultat,
            "date_resultat": date_affichee(resultat["date_sauvegarde"]) if resultat else None,
            "date_application": date_affichee(resultat["applique_le"]) if resultat else None,
        },
    )


def mot_de_passe_oublie(request):
    if not settings.EMAIL_DISPONIBLE:
        return render(request, "suivi/mot_de_passe_oublie.html")
    return auth_views.PasswordResetView.as_view(
        template_name="suivi/mot_de_passe_oublie.html",
        email_template_name="suivi/emails/mot_de_passe_reinitialisation.txt",
        subject_template_name=(
            "suivi/emails/mot_de_passe_reinitialisation_objet.txt"
        ),
        success_url=reverse_lazy("mot_de_passe_oublie_envoye"),
    )(request)


def deconnexion(request):
    logout(request)
    return redirect("connexion")


@acces_requis
def mon_compte(request):
    formulaire = ProfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and formulaire.is_valid():
        formulaire.save()
        messages.success(request, "Votre identité a été mise à jour.")
        return redirect("mon_compte")
    affectations = (
        AffectationClasse.objects.filter(appartenance__utilisateur=request.user)
        .select_related("classe", "classe__ecole")
        .order_by("-classe__annee_scolaire", "classe__ecole__nom", "classe__nom")
    )
    return render(
        request,
        "suivi/mon_compte.html",
        {"formulaire": formulaire, "affectations": affectations},
    )


def accepter_invitation_vue(request, selecteur, jeton):
    invitation = get_object_or_404(Invitation, selecteur=selecteur)
    if not invitation_est_utilisable(invitation, jeton):
        return render(
            request,
            "suivi/accepter_invitation.html",
            {"invitation": invitation, "invalide": True},
        )
    compte_existant = Utilisateur.objects.filter(
        email__iexact=invitation.email
    ).first()
    formulaire = None
    if not compte_existant:
        formulaire = CreationCompteInvitationForm(
            request.POST or None, email=invitation.email
        )
    if request.method == "POST":
        if compte_existant:
            utilisateur = authenticate(
                request,
                username=request.POST.get("nom_utilisateur", "").strip(),
                password=request.POST.get("mot_de_passe", ""),
            )
            if not utilisateur:
                messages.error(
                    request, "Nom d'utilisateur ou mot de passe incorrect."
                )
            else:
                try:
                    accepter_invitation(
                        utilisateur=utilisateur, invitation=invitation, jeton=jeton
                    )
                except (PermissionDenied, ValidationError):
                    messages.error(
                        request,
                        "Invitation invalide, expirée ou destinée à une autre adresse.",
                    )
                else:
                    logout(request)
                    return render(
                        request,
                        "suivi/accepter_invitation.html",
                        {"invitation": invitation, "acceptee": True},
                    )
        elif formulaire.is_valid():
            try:
                creer_compte_et_accepter_invitation(
                    invitation=invitation,
                    jeton=jeton,
                    username=formulaire.cleaned_data["username"],
                    first_name=formulaire.cleaned_data["first_name"],
                    last_name=formulaire.cleaned_data["last_name"],
                    password=formulaire.cleaned_data["password1"],
                )
            except (PermissionDenied, ValidationError) as erreur:
                detail = (
                    "; ".join(erreur.messages)
                    if hasattr(erreur, "messages")
                    else "Invitation invalide ou expirée."
                )
                formulaire.add_error(None, detail)
            else:
                logout(request)
                return render(
                    request,
                    "suivi/accepter_invitation.html",
                    {"invitation": invitation, "acceptee": True},
                )
    return render(
        request,
        "suivi/accepter_invitation.html",
        {
            "invitation": invitation,
            "compte_existant": compte_existant,
            "formulaire": formulaire,
        },
    )


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------


def _grouper_classes_par_annee(classes, toutes):
    """Regroupe des classes annotées de ``nb_eleves`` par année scolaire
    décroissante, avec le statut de chaque groupe (voir Classe.statut_annee).
    Sans ``toutes``, seules les années à partir de l'année courante sont
    gardées. Renvoie (groupes, a_des_annees_passees)."""
    classes = list(classes)
    annee_courante = annee_scolaire_pour(timezone.localdate())
    a_des_annees_passees = any(c.annee_scolaire < annee_courante for c in classes)
    if not toutes:
        classes = [c for c in classes if c.annee_scolaire >= annee_courante]

    groupes = []
    for annee in sorted({c.annee_scolaire for c in classes}, reverse=True):
        classes_annee = [c for c in classes if c.annee_scolaire == annee]
        groupes.append(
            {
                "annee": annee,
                "statut": classes_annee[0].statut_annee,
                "classes": classes_annee,
            }
        )
    return groupes, a_des_annees_passees


@acces_requis
def accueil(request):
    ecole = ecole_courante(request)
    if (settings.MODE_LOCAL and est_direction(request.user, ecole)
            and lire_resultat(Path(settings.DATABASES["default"]["NAME"]).parent)):
        return redirect("sauvegardes_locales")
    classes = classes_accessibles(request.user, VOIR_CLASSE, ecole).annotate(
        nb_eleves=Count(
            "scolarites__eleve",
            filter=Q(scolarites__eleve__archive_le__isnull=True),
            distinct=True,
        )
    )
    toutes = request.GET.get("toutes") == "1"
    groupes, a_des_annees_passees = _grouper_classes_par_annee(classes, toutes)

    return render(
        request,
        "suivi/accueil.html",
        {
            "groupes": groupes,
            "toutes": toutes,
            "a_des_annees_passees": a_des_annees_passees,
        },
    )


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


def _bilans_par_eleve(eleves, classe, filtre="classe"):
    """Nombre de bilans, avec la même logique de filtre que ``_progression``.

    - ``"classe"`` : bilans de la scolarité de l'élève dans cette classe,
      dont la date tombe bien dans l'année scolaire de la classe (une
      scolarité est déjà propre à cette année, mais on vérifie la date en
      plus, par défense) ;
    - ``"tous"`` : tous les bilans de l'élève, toutes années confondues ;
    - ``"PS"``, ``"MS"`` ou ``"GS"`` : les bilans rattachés à une scolarité
      où l'élève avait ce niveau, quelle que soit la classe ou l'année (il
      peut, rarement, y en avoir eu plusieurs).
    """
    if filtre == "tous":
        compte = dict(
            Bilan.objects.filter(
                scolarite__eleve__in=eleves, supprime_le__isnull=True
            )
            .values("scolarite__eleve_id")
            .annotate(n=Count("pk"))
            .values_list("scolarite__eleve_id", "n")
        )
    elif filtre in {"PS", "MS", "GS"}:
        compte = dict(
            Bilan.objects.filter(
                scolarite__eleve__in=eleves,
                scolarite__niveau=filtre,
                supprime_le__isnull=True,
            )
            .values("scolarite__eleve_id")
            .annotate(n=Count("pk"))
            .values_list("scolarite__eleve_id", "n")
        )
    else:  # "classe" : bilans de cette classe, datés dans son année scolaire
        debut, fin = bornes_annee_scolaire(classe.annee_scolaire)
        compte = dict(
            Bilan.objects.filter(
                scolarite__classe=classe,
                scolarite__eleve__in=eleves,
                date_bilan__gte=debut,
                date_bilan__lte=fin,
                supprime_le__isnull=True,
            )
            .values("scolarite__eleve_id")
            .annotate(n=Count("pk"))
            .values_list("scolarite__eleve_id", "n")
        )
    for e in eleves:
        e.nb_bilans = compte.get(e.pk, 0)


@acces_requis
def classe_detail(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(
        request.user, pk, VOIR_LISTE_ELEVES, ecole=ecole
    )
    eleves = list(classe.eleves)
    suivi_complet = autorise(request.user, VOIR_SUIVI, classe, ecole=ecole)
    peut_generer = autorise(request.user, GENERER_CARNET, classe, ecole=ecole)
    peut_gerer_eleves = autorise(
        request.user, GERER_ELEVES_CLASSE, classe, ecole=ecole
    )
    affectation = affectation_active(request.user, classe)
    vue_minimale = bool(
        affectation and affectation.type == AffectationClasse.CONTRIBUTEUR
    )
    if vue_minimale:
        groupes_noms = {}
        for eleve in eleves:
            cle = (eleve.prenom.casefold(), eleve.nom[:1].casefold(), eleve.niveau)
            groupes_noms.setdefault(cle, []).append(eleve)
        for groupe in groupes_noms.values():
            for eleve in groupe:
                eleve.nom_affiche = str(eleve) if len(groupe) > 1 else eleve.nom_court
    else:
        for eleve in eleves:
            eleve.nom_affiche = str(eleve)
    filtre = request.GET.get("niveaux", "classe")
    if filtre not in FILTRES_NIVEAU_CLASSE:
        filtre = "classe"
    total = 0
    if suivi_complet:
        total = _progression(eleves, ecole, filtre)
        _bilans_par_eleve(eleves, classe, filtre)
    return render(
        request,
        "suivi/classe.html",
        {
            "classe": classe,
            "eleves": eleves,
            "total_competences": total,
            "filtre": filtre,
            "suivi_complet": suivi_complet,
            "peut_generer": peut_generer,
            "peut_gerer_eleves": peut_gerer_eleves,
            "vue_minimale": vue_minimale,
        },
    )


@acces_requis
def collaborateurs_classe(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(
        request.user, pk, VOIR_AFFECTATIONS_CLASSE, ecole=ecole
    )
    affectations = classe.affectations.select_related(
        "appartenance__utilisateur"
    ).order_by("appartenance__utilisateur__last_name", "date_debut")
    return render(
        request,
        "suivi/collaborateurs_classe.html",
        {"classe": classe, "affectations": affectations},
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


def _scolarites_visibles(utilisateur, eleve):
    courante = eleve.scolarite_courante()
    if courante is None:
        return Scolarite.objects.none(), None
    ids = [courante.pk]
    if AccesParcoursEleve.objects.filter(
        eleve=eleve, classe=courante.classe
    ).exists() and autorise(utilisateur, VOIR_SUIVI, courante.classe):
        ids = list(eleve.scolarites.values_list("pk", flat=True))
    return eleve.scolarites.filter(pk__in=ids), courante


def _observations_visibles(utilisateur, eleve):
    scolarites, courante = _scolarites_visibles(utilisateur, eleve)
    if courante is None:
        return Observation.objects.none()
    condition_dates = Q()
    for annee in scolarites.values_list("annee_scolaire", flat=True):
        debut, fin = bornes_annee_scolaire(annee)
        condition_dates |= Q(date_observation__range=(debut, fin))
    traces = Trace.objects.filter(
        Q(scolarite=courante)
        | Q(scolarite__in=scolarites.exclude(pk=courante.pk), visible_carnet=True),
        supprime_le__isnull=True,
    )
    return eleve.observations.filter(
        condition_dates | Q(traces__in=traces)
    ).distinct().prefetch_related(Prefetch("traces", queryset=traces))


@acces_requis
def saisie_eleve(request, pk):
    """L'écran du quotidien : un enfant, tout ce qu'il sait faire."""
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(
        request.user,
        pk,
        VOIR_SUIVI,
        ecole=ecole,
        actifs_seulement=True,
    )
    filtre = request.GET.get("niveaux", "tous")
    niveaux = None if filtre == "tous" else [filtre]

    etats = {o.competence_id: o for o in _observations_visibles(request.user, eleve)}
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
def contribuer_eleve(request, pk):
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(
        request.user,
        pk,
        CONTRIBUER,
        ecole=ecole,
        actifs_seulement=True,
    )
    domaines = [(d, d.visibles) for d in _arbre(ecole) if d.visibles]
    return render(
        request,
        "suivi/contribuer_eleve.html",
        {"eleve": eleve, "domaines": domaines},
    )


@acces_requis
def choisir_competence(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole)
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
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole)
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


def _contexte_grille_competence(
    request, pk, competence_pk, operation=VOIR_SUIVI
):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, operation, ecole=ecole)
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
    contexte = _contexte_grille_competence(
        request, pk, competence_pk, GENERER_CARNET
    )
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
    journaliser(
        request.user,
        "pdf.grille_genere",
        contexte["classe"],
        nouvelles={
            "competence_id": contexte["competence"].pk,
            "taille": len(contenu),
        },
    )
    journaliser(
        request.user,
        "pdf.grille_telecharge",
        contexte["classe"],
        nouvelles={"competence_id": contexte["competence"].pk},
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
    eleve = charger_eleve_autorise(
        request.user,
        eleve_pk,
        MODIFIER_ETAT,
        ecole=ecole,
        actifs_seulement=True,
    )
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)

    obs = Observation.objects.filter(
        eleve=eleve,
        competence=competence,
    ).first()

    suivant = SUITE[obs.statut if obs else None]

    obs = modifier_etat(
        utilisateur=request.user,
        eleve=eleve,
        competence=competence,
        statut=suivant,
    )

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


def _charger_trace_media(request, trace_pk, operation):
    ecole = ecole_courante(request)
    trace_obj = get_object_or_404(
        Trace.objects.select_related(
            "auteur",
            "observation__eleve",
            "scolarite__classe",
        ),
        pk=trace_pk,
        observation__eleve__ecole=ecole,
        supprime_le__isnull=True,
    )
    if not autorise(request.user, operation, trace_obj, ecole=ecole):
        raise Http404
    return trace_obj


@never_cache
@acces_requis
@require_safe
def afficher_media_trace(request, trace_pk):
    trace_obj = _charger_trace_media(request, trace_pk, VOIR_MEDIA)
    nom = Path(trace_obj.photo.name).name
    return FileResponse(
        default_storage.open(trace_obj.photo.name, "rb"),
        content_type=mimetypes.guess_type(nom)[0] or "application/octet-stream",
        filename=nom,
    )


@never_cache
@acces_requis
@require_safe
def telecharger_media_trace(request, trace_pk):
    trace_obj = _charger_trace_media(
        request, trace_pk, TELECHARGER_MEDIA_ORIGINAL
    )
    nom = Path(trace_obj.photo.name).name
    try:
        taille = trace_obj.photo.size
    except OSError:
        taille = None
    journaliser(
        request.user,
        "media.original_telecharge",
        trace_obj,
        nouvelles={
            "nom_fichier": nom,
            "type_mime": mimetypes.guess_type(nom)[0],
            "taille": taille,
        },
    )
    return FileResponse(
        default_storage.open(trace_obj.photo.name, "rb"),
        as_attachment=True,
        filename=nom,
        content_type=mimetypes.guess_type(nom)[0] or "application/octet-stream",
    )


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
    charger_eleve_autorise(
        request.user, eleve_pk, CONTRIBUER, ecole=ecole
    )
    trace_obj = get_object_or_404(
        Trace,
        pk=trace_pk,
        observation__eleve_id=eleve_pk,
        observation__competence_id=competence_pk,
        observation__eleve__ecole=ecole,
        supprime_le__isnull=True,
    )
    supprimer_trace_logiquement(utilisateur=request.user, trace=trace_obj)
    messages.success(request, "Trace supprimée.")
    return redirect("trace", eleve_pk=eleve_pk, competence_pk=competence_pk)


@acces_requis
def restaurer_trace_vue(request, eleve_pk, competence_pk, trace_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    charger_eleve_autorise(request.user, eleve_pk, MODIFIER_ETAT, ecole=ecole)
    trace_obj = get_object_or_404(
        Trace,
        pk=trace_pk,
        observation__eleve_id=eleve_pk,
        observation__competence_id=competence_pk,
        observation__eleve__ecole=ecole,
        supprime_le__isnull=False,
    )
    restaurer_trace(utilisateur=request.user, trace=trace_obj)
    messages.success(request, "Trace restaurée.")
    return redirect("trace", eleve_pk=eleve_pk, competence_pk=competence_pk)


@acces_requis
def basculer_visibilite_trace(request, eleve_pk, competence_pk, trace_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    charger_eleve_autorise(
        request.user, eleve_pk, MODIFIER_ETAT, ecole=ecole
    )
    trace_obj = get_object_or_404(
        Trace,
        pk=trace_pk,
        observation__eleve_id=eleve_pk,
        observation__competence_id=competence_pk,
        observation__eleve__ecole=ecole,
        supprime_le__isnull=True,
    )
    definir_visibilite_trace(
        utilisateur=request.user,
        trace=trace_obj,
        visible=not trace_obj.visible_carnet,
    )
    etat = "affichée dans le carnet" if trace_obj.visible_carnet else "masquée du carnet"
    messages.success(request, f"Trace {etat}.")
    return redirect("trace", eleve_pk=eleve_pk, competence_pk=competence_pk)


def _editer_trace(request, eleve_pk, competence_pk, trace_pk=None):
    """Ajouter ou modifier une trace datée sans écraser les précédentes."""
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(
        request.user,
        eleve_pk,
        CONTRIBUER,
        ecole=ecole,
        actifs_seulement=True,
    )
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    obs = Observation.objects.filter(eleve=eleve, competence=competence).first()
    scolarite_courante = eleve.scolarite_courante()
    trace_obj = None
    if trace_pk is not None:
        trace_obj = get_object_or_404(
            Trace,
            pk=trace_pk,
            observation__eleve=eleve,
            observation__competence=competence,
            scolarite=scolarite_courante,
            supprime_le__isnull=True,
        )
        if not (
            autorise(request.user, MODIFIER_ETAT, eleve, ecole=ecole)
            or trace_obj.auteur_id == request.user.pk
        ):
            raise Http404

    if request.method == "POST":
        if not autorise(request.user, CONTRIBUER, eleve, ecole=ecole):
            return HttpResponseForbidden("Contribution non autorisée.")
        scolarite = scolarite_courante
        if scolarite is None:
            return HttpResponseForbidden("Aucune scolarité n'est associée à cet élève.")
        ancien_nom_photo = (
            trace_obj.photo.name if trace_obj and trace_obj.photo else ""
        )
        valeurs = {
            "commentaire": request.POST.get("commentaire", "").strip(),
            "visible_carnet": request.POST.get("visible_carnet") == "on",
        }
        photo = trace_obj.photo if trace_obj else None
        if request.POST.get("retirer_photo"):
            photo = None
        if request.FILES.get("photo"):
            photo = request.FILES["photo"]
        valeurs["photo"] = photo
        date = request.POST.get("date_observation")
        if date:
            valeurs["date_observation"] = date
        with transaction.atomic():
            trace_obj = enregistrer_trace(
                utilisateur=request.user,
                eleve=eleve,
                competence=competence,
                scolarite=scolarite,
                trace=trace_obj,
                valeurs=valeurs,
            )
            nouveau_nom_photo = trace_obj.photo.name if trace_obj.photo else ""
            if ancien_nom_photo and ancien_nom_photo != nouveau_nom_photo:
                _supprimer_media_apres_validation(ancien_nom_photo)
        messages.success(request, f"Trace enregistrée pour {eleve.prenom}.")
        return redirect("trace", eleve_pk=eleve.pk, competence_pk=competence.pk)

    traces = (
        obs.traces.filter(
            scolarite=scolarite_courante,
            supprime_le__isnull=True,
        ).select_related("scolarite")
        if obs
        else Trace.objects.none()
    )
    if not autorise(request.user, VOIR_SUIVI, eleve, ecole=ecole):
        traces = traces.filter(auteur=request.user)
    responsable = autorise(request.user, MODIFIER_ETAT, eleve, ecole=ecole)
    for trace_conservee in traces:
        trace_conservee.peut_modifier = (
            responsable or trace_conservee.auteur_id == request.user.pk
        )
        trace_conservee.peut_telecharger_original = autorise(
            request.user,
            TELECHARGER_MEDIA_ORIGINAL,
            trace_conservee,
            ecole=ecole,
        )
    traces_supprimees = Trace.objects.none()
    if responsable and obs:
        traces_supprimees = obs.traces.filter(
            scolarite=scolarite_courante,
            supprime_le__isnull=False,
        )
    return render(
        request,
        "suivi/trace.html",
        {
            "eleve": eleve,
            "competence": competence,
            "obs": obs,
            "trace_obj": trace_obj,
            "traces": traces,
            "traces_supprimees": traces_supprimees,
            "responsable": responsable,
            "suivi_complet": autorise(
                request.user, VOIR_SUIVI, eleve, ecole=ecole
            ),
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


def _contexte_carnet(request, pk, options=None, operation=PREVISUALISER_CARNET):
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(
        request.user, pk, operation, ecole=ecole
    )
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

    scolarites_visibles, _ = _scolarites_visibles(request.user, eleve)
    etats = {
        o.competence_id: o
        for o in _observations_visibles(request.user, eleve).select_related(
            "competence"
        )
    }
    for observation in etats.values():
        observation.traces_carnet = [
            trace
            for trace in observation.traces.all()
            if trace.visible_carnet and trace.supprime_le is None
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
            domaines.append(
                (
                    d,
                    _regrouper_lignes(
                        eleve, lignes, regroupement, scolarites_visibles
                    ),
                )
            )

    scolarite = eleve.scolarite_courante()
    bilans = (
        Bilan.objects.filter(
            scolarite__eleve=eleve,
            scolarite__in=scolarites_visibles,
            visible_carnet=True,
            supprime_le__isnull=True,
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
        "peut_generer": autorise(
            request.user, GENERER_CARNET, eleve, ecole=ecole
        ),
    }


def _regrouper_lignes(eleve, lignes, regroupement, scolarites=None):
    if regroupement == "aucun":
        return [(None, lignes)]

    filtre_bilans = Bilan.objects.filter(
        scolarite__eleve=eleve, supprime_le__isnull=True
    )
    if scolarites is not None:
        filtre_bilans = filtre_bilans.filter(scolarite__in=scolarites)
    bilans = list(
        filtre_bilans
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
            annee = annee_scolaire_pour(observation.date_observation)
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
    contenu, nom = _contenu_pdf_carnet(request, pk, operation=GENERER_CARNET)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    journaliser(
        request.user,
        "pdf.carnet_telecharge",
        eleve,
        nouvelles={"nom_fichier": nom, "taille": len(contenu)},
    )
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


def _contenu_pdf_carnet(request, pk, options=None, operation=GENERER_CARNET):
    contexte = _contexte_carnet(request, pk, options, operation)
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
    journaliser(
        request.user,
        "pdf.carnet_genere",
        contexte["eleve"],
        nouvelles={
            "mode": contexte["mode"],
            "colonnes": contexte["colonnes"],
            "regroupement": contexte["regroupement"],
            "taille": len(contenu),
        },
    )
    return contenu, f"carnet-{nom}.pdf"


@never_cache
@acces_requis
def preparer_edition(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(
        request.user, pk, GENERER_CARNET, ecole=ecole
    )
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
            journaliser(
                request.user,
                "zip.classe_genere",
                classe,
                nouvelles={
                    "nombre_eleves": len(selection),
                    "taille": len(archive.getvalue()),
                },
            )
            journaliser(
                request.user,
                "zip.classe_telecharge",
                classe,
                nouvelles={"nombre_eleves": len(selection)},
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
    for classe in classes:
        classe.peut_etre_activee = bool(
            classe.etat == Classe.PREPARATION
            and classe.responsables_actifs().exists()
        )
    toutes = request.GET.get("toutes") == "1"
    groupes, a_des_annees_passees = _grouper_classes_par_annee(classes, toutes)
    eleves_archives = ecole.eleves.filter(archive_le__isnull=False)
    nb_competences = Competence.objects.filter(
        domaine__ecole=ecole, active=True
    ).count()
    return render(
        request,
        "suivi/gestion.html",
        {
            "groupes": groupes,
            "toutes": toutes,
            "a_des_annees_passees": a_des_annees_passees,
            "nb_competences": nb_competences,
            "eleves_archives": eleves_archives,
        },
    )


@direction_requise
def equipe_ecole(request):
    ecole = ecole_courante(request)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "inviter":
                invitation, jeton = inviter(
                    utilisateur=request.user,
                    ecole=ecole,
                    email=request.POST.get("email", ""),
                )
                lien = request.build_absolute_uri(
                    reverse(
                        "accepter_invitation",
                        args=[invitation.selecteur, jeton],
                    )
                )
                request.session["lien_invitation_creee"] = lien
                if not settings.EMAIL_DISPONIBLE:
                    messages.warning(
                        request,
                        "Invitation créée. L’envoi de courriel est désactivé : "
                        "copiez le lien affiché ci-dessous et transmettez-le "
                        "vous-même.",
                    )
                elif envoyer_email_invitation(
                    utilisateur=request.user, invitation=invitation, lien=lien
                ):
                    messages.success(
                        request,
                        f"Invitation envoyée par e-mail à {invitation.email}. "
                        "Le lien reste aussi affiché ci-dessous en secours, "
                        "au cas où l’e-mail n’arriverait pas.",
                    )
                else:
                    messages.warning(
                        request,
                        "Invitation créée, mais l’envoi de l’e-mail a "
                        "échoué. Copiez le lien affiché ci-dessous et "
                        "transmettez-le vous-même.",
                    )
            elif action == "revoquer_invitation":
                revoquer_invitation(
                    utilisateur=request.user,
                    invitation=get_object_or_404(
                        Invitation, pk=request.POST.get("invitation"), ecole=ecole
                    ),
                )
            elif action == "affecter":
                classe = get_object_or_404(
                    Classe, pk=request.POST.get("classe"), ecole=ecole
                )
                if (
                    classe.statut_annee in {"passee", "ancienne"}
                    and request.POST.get("historique") != "1"
                ):
                    raise ValidationError(
                        "Affichez les années passées avant d’y attribuer une fonction."
                    )
                attribuer_affectation(
                    utilisateur=request.user,
                    appartenance=get_object_or_404(
                        AppartenanceEcole,
                        pk=request.POST.get("appartenance"),
                        ecole=ecole,
                    ),
                    classe=classe,
                    type=request.POST.get("type"),
                    date_fin=request.POST.get("date_fin") or None,
                    motif=request.POST.get("motif", ""),
                )
                messages.success(request, "Affectation enregistrée.")
            elif action == "remplacer_responsable":
                affectation = get_object_or_404(
                    AffectationClasse,
                    pk=request.POST.get("affectation"),
                    classe__ecole=ecole,
                    type=AffectationClasse.RESPONSABLE,
                    etat=AffectationClasse.ACTIVE,
                )
                remplacement = get_object_or_404(
                    AppartenanceEcole,
                    pk=request.POST.get("remplacement"),
                    ecole=ecole,
                )
                remplacer_responsable(
                    utilisateur=request.user,
                    affectation=affectation,
                    appartenance_remplacante=remplacement,
                    motif=request.POST.get("motif", ""),
                )
                messages.success(request, "Responsable remplacé.")
            elif action in {"terminer_affectation", "suspendre_affectation"}:
                affectation = get_object_or_404(
                    AffectationClasse,
                    pk=request.POST.get("affectation"),
                    classe__ecole=ecole,
                )
                if action == "terminer_affectation":
                    terminer_affectation(
                        utilisateur=request.user, affectation=affectation
                    )
                else:
                    suspendre_affectation_urgence(
                        utilisateur=request.user,
                        affectation=affectation,
                        motif=request.POST.get("motif", ""),
                    )
                messages.success(
                    request,
                    "Affectation terminée."
                    if action == "terminer_affectation"
                    else "Affectation suspendue en urgence.",
                )
        except (ValidationError, PermissionDenied) as erreur:
            detail = (
                "; ".join(erreur.messages)
                if hasattr(erreur, "messages")
                else "Action refusée."
            )
            messages.error(request, detail)
        vue_retour = request.POST.get("vue")
        historique_retour = request.POST.get("historique") == "1"
        if vue_retour in {"classes", "personnes"}:
            suffixe = f"?vue={vue_retour}"
            if historique_retour:
                suffixe += "&historique=1"
            return redirect(f"{reverse('equipe_ecole')}{suffixe}")
        return redirect("equipe_ecole")

    appartenances = list(
        ecole.appartenances.select_related("utilisateur").prefetch_related(
            "responsabilites", "affectations_classes__classe"
        )
    )
    aujourd_hui = timezone.localdate()
    membres_affectables = [
        appartenance
        for appartenance in appartenances
        if appartenance.est_active(aujourd_hui)
    ]
    for appartenance in appartenances:
        for affectation in appartenance.affectations_classes.all():
            affectation.est_active_aujourdhui = affectation.est_active(aujourd_hui)
            if not affectation.est_active_aujourdhui:
                continue
            affectation.peut_terminer_directement = peut_terminer_affectation(
                request.user, affectation, date=aujourd_hui
            )
            if affectation.type == AffectationClasse.RESPONSABLE:
                affectation.remplacants = [
                    candidat
                    for candidat in membres_affectables
                    if candidat.utilisateur_id != appartenance.utilisateur_id
                    and not candidat.affectations_classes.filter(
                        classe=affectation.classe,
                        etat=AffectationClasse.ACTIVE,
                        date_debut__lte=aujourd_hui,
                    )
                    .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=aujourd_hui))
                    .exists()
                ]
    vue_equipe = request.GET.get("vue", "classes")
    if vue_equipe not in {"classes", "personnes"}:
        vue_equipe = "classes"
    afficher_historique = request.GET.get("historique") == "1"

    def est_presente_ou_future(relation):
        return relation.etat == relation.ACTIVE and (
            relation.date_fin is None or relation.date_fin >= aujourd_hui
        )

    def preparer_affectation(affectation):
        affectation.est_future = (
            affectation.etat == AffectationClasse.ACTIVE
            and affectation.date_debut > aujourd_hui
        )
        affectation.est_presente_ou_future = (
            est_presente_ou_future(affectation)
            and affectation.classe.statut_annee in {"courante", "future"}
        )
        affectation.classe_historique = affectation.classe.statut_annee in {
            "passee",
            "ancienne",
        }
        return affectation

    affectations_par_classe = {}
    for appartenance in appartenances:
        affectations = [
            preparer_affectation(affectation)
            for affectation in appartenance.affectations_classes.all()
        ]
        affectations.sort(
            key=lambda affectation: (
                -int(affectation.classe.annee_scolaire[:4]),
                affectation.classe.ordre,
                affectation.classe.nom.casefold(),
                -affectation.date_debut.toordinal(),
            )
        )
        appartenance.affectations_visibles = [
            affectation
            for affectation in affectations
            if affectation.est_presente_ou_future
        ]
        appartenance.affectations_historiques = [
            affectation
            for affectation in affectations
            if not affectation.est_presente_ou_future
        ]
        for affectation in affectations:
            affectations_par_classe.setdefault(affectation.classe_id, []).append(
                affectation
            )

    anomalies = list(
        ecole.anomalies_gouvernance.filter(resolue_le__isnull=True).select_related(
            "classe"
        )
    )
    anomalies_par_classe = {
        anomalie.classe_id: anomalie
        for anomalie in anomalies
        if anomalie.classe_id is not None
    }
    classes_equipe = list(
        ecole.classes.order_by("-annee_scolaire", "ordre", "nom")
    )
    for classe in classes_equipe:
        affectations = affectations_par_classe.get(classe.pk, [])
        classe.affectations_visibles = [
            affectation
            for affectation in affectations
            if affectation.est_presente_ou_future
        ]
        classe.affectations_historiques = [
            affectation
            for affectation in affectations
            if not affectation.est_presente_ou_future
        ]
        classe.anomalie_ouverte = anomalies_par_classe.get(classe.pk)

    classes_visibles = [
        classe
        for classe in classes_equipe
        if afficher_historique
        or classe.statut_annee in {"courante", "future"}
        or classe.anomalie_ouverte
    ]
    classes_affectables = [
        classe
        for classe in classes_equipe
        if afficher_historique
        or classe.statut_annee in {"courante", "future"}
    ]
    personnes_visibles = [
        appartenance
        for appartenance in appartenances
        if afficher_historique or est_presente_ou_future(appartenance)
    ]
    invitations = list(ecole.invitations.all())
    maintenant = timezone.now()
    for invitation in invitations:
        invitation.est_expiree = bool(
            invitation.etat == Invitation.EN_ATTENTE
            and invitation.expire_le < maintenant
        )
    return render(
        request,
        "suivi/equipe.html",
        {
            "appartenances": personnes_visibles,
            "membres_affectables": membres_affectables,
            "invitations": invitations,
            "lien_invitation_creee": request.session.pop(
                "lien_invitation_creee", None
            ),
            "classes": classes_equipe,
            "classes_visibles": classes_visibles,
            "classes_affectables": classes_affectables,
            "types_affectation": AffectationClasse.TYPES,
            "anomalies": anomalies,
            "vue_equipe": vue_equipe,
            "afficher_historique": afficher_historique,
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
                return render(
                    request,
                    "suivi/creer_classe.html",
                    {"nom": nom, "annee_scolaire": annee_scolaire},
                )
            return redirect("importer_eleves", pk=classe.pk)
        messages.error(
            request,
            "Donnez un nom et une année scolaire au format 2027-2028.",
        )
        return render(
            request,
            "suivi/creer_classe.html",
            {"nom": nom, "annee_scolaire": annee_scolaire},
        )
    return render(request, "suivi/creer_classe.html")


@direction_requise
def activer_classe_vue(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    try:
        activer_classe(utilisateur=request.user, classe=classe)
    except ValidationError as erreur:
        messages.error(request, "; ".join(erreur.messages))
    else:
        messages.success(request, f"La classe {classe.nom} est maintenant active.")
    return redirect("gestion")


@acces_requis
def parcours_eleve(request, pk):
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole)
    retour_pk = request.POST.get("retour") or request.GET.get("retour")
    retour_classe = (
        Classe.objects.filter(pk=retour_pk, ecole=ecole).first() if retour_pk else None
    )
    direction = est_direction(request.user, ecole)
    classe = retour_classe or eleve.classe
    if not direction and (
        classe is None
        or not eleve.scolarites.filter(classe=classe).exists()
        or not autorise(
            request.user, GERER_ELEVES_CLASSE, classe, ecole=ecole
        )
    ):
        raise Http404

    def _retour_url():
        url = reverse("parcours_eleve", args=[eleve.pk])
        return f"{url}?retour={retour_classe.pk}" if retour_classe else url

    if request.method == "POST" and request.POST.get("action") == "reactiver":
        desarchiver(utilisateur=request.user, eleve=eleve, classe=classe)
        ou = _message_scolarite_courante(eleve)
        if ou:
            messages.success(request, f"{eleve.prenom} est de nouveau actif, dans {ou}.")
        else:
            messages.success(
                request,
                f"{eleve.prenom} est de nouveau actif, mais n'a pas encore de "
                "scolarité pour l'année en cours : ajoutez-en une ci-dessous.",
            )
        return redirect(_retour_url())

    if request.method == "POST" and request.POST.get("action") == "identite":
        prenom = request.POST.get("prenom", "").strip()
        if not prenom:
            messages.error(request, "Le prénom est obligatoire.")
        else:
            annee = request.POST.get("annee_naissance", "").strip()
            modifier_identite(
                utilisateur=request.user,
                eleve=eleve,
                classe=classe,
                valeurs={
                    "prenom": prenom,
                    "nom": request.POST.get("nom", "").strip(),
                    "annee_naissance": int(annee) if annee.isdigit() else None,
                },
            )
            messages.success(request, "Identité de l'élève enregistrée.")
            return redirect(_retour_url())

    if request.method == "POST" and request.POST.get("action") == "scolarite":
        if not direction:
            raise Http404
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
            return redirect(_retour_url())

    return render(
        request,
        "suivi/parcours_eleve.html",
        {
            "eleve": eleve,
            "classes": ecole.classes.all(),
            "scolarites": eleve.scolarites.select_related("classe"),
            "retour_classe": retour_classe,
            "direction": direction,
        },
    )


NIVEAU_SUIVANT = {"PS": "MS", "MS": "GS", "GS": None}


def _annee_precedente(annee_scolaire):
    debut = int(re.match(r"(\d{4})", annee_scolaire).group(1))
    return f"{debut - 1}-{debut}"


NIVEAUX_VALIDES = {"PS", "MS", "GS"}


def _niveau_defaut_page(request):
    valeur = request.GET.get("niveau_defaut") or request.POST.get("niveau_defaut")
    return valeur if valeur in NIVEAUX_VALIDES else "PS"


@acces_requis
def importer_eleves(request, pk):
    """Coller la liste de la classe, un enfant par ligne."""
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(
        request.user, pk, GERER_ELEVES_CLASSE, ecole=ecole
    )
    direction = est_direction(request.user, ecole)
    niveau_defaut_page = _niveau_defaut_page(request)
    action = request.POST.get("action") if request.method == "POST" else None
    if not direction and action in {
        "retirer",
        "deplacer",
        "valider_rapprochement",
    }:
        raise Http404

    if action == "valider_rapprochement":
        demande = get_object_or_404(
            DemandeRapprochementEleve,
            pk=request.POST.get("demande"),
            ecole=ecole,
            classe=classe,
            etat=DemandeRapprochementEleve.EN_ATTENTE,
        )
        eleve = get_object_or_404(
            Eleve, pk=request.POST.get("eleve"), ecole=ecole
        )
        try:
            valider_rapprochement(
                utilisateur=request.user, demande=demande, eleve=eleve
            )
        except ValidationError as erreur:
            messages.error(request, "; ".join(erreur.messages))
        else:
            messages.success(
                request,
                f"Le dossier de {eleve.prenom} a été rapproché de {classe}.",
            )
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST" and request.POST.get("action") == "affecter_existant":
        eleve = get_object_or_404(
            Eleve, pk=request.POST.get("eleve"), ecole=ecole
        )
        if not direction and not eleve.scolarites.filter(classe=classe).exists():
            raise Http404
        niveau = request.POST.get("niveau")
        if niveau not in NIVEAUX_VALIDES:
            niveau = niveau_defaut_page
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
                niveau_inchange = deja_dans_classe and scolarite.niveau == niveau
                if deja_dans_classe:
                    modifier_niveau_courant(
                        utilisateur=request.user,
                        scolarite=scolarite,
                        niveau=niveau,
                    )
                else:
                    scolarite.classe = classe
                    scolarite.niveau = niveau
                    scolarite.save(
                        update_fields=["classe", "niveau", "modifie_le"]
                    )
            else:
                deja_dans_classe = False
                niveau_inchange = False
                Scolarite.objects.create(
                    eleve=eleve,
                    classe=classe,
                    annee_scolaire=classe.annee_scolaire,
                    niveau=niveau,
                )

        if deja_dans_classe and not reactive:
            if niveau_inchange:
                messages.info(request, f"{eleve.prenom} est déjà dans {classe}.")
            else:
                messages.success(
                    request, f"Niveau de {eleve.prenom} mis à jour : {niveau}."
                )
        else:
            messages.success(request, f"{eleve.prenom} a été ajouté à {classe}.")
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST" and request.POST.get("action") == "retirer":
        scolarite = get_object_or_404(
            Scolarite,
            eleve__pk=request.POST.get("eleve"),
            eleve__ecole=ecole,
            classe=classe,
        )
        if scolarite.bilans.exists() or scolarite.traces.exists():
            messages.error(
                request,
                f"{scolarite.eleve.prenom} a des bilans ou des observations "
                f"datées enregistrés pour {classe.annee_scolaire} : "
                "utilisez plutôt « Déplacer vers une autre classe », ou "
                "supprimez d'abord ces éléments.",
            )
        else:
            prenom = scolarite.eleve.prenom
            scolarite.delete()
            messages.success(
                request,
                f"{prenom} a été retiré de {classe} : il n'a plus de scolarité "
                f"pour {classe.annee_scolaire}.",
            )
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST" and request.POST.get("action") == "retirer_et_archiver":
        scolarite = get_object_or_404(
            Scolarite,
            eleve__pk=request.POST.get("eleve"),
            eleve__ecole=ecole,
            classe=classe,
        )
        eleve = scolarite.eleve
        archiver(utilisateur=request.user, eleve=eleve, classe=classe)
        messages.success(
            request,
            f"{eleve.prenom} a été retiré de {classe} et archivé sans supprimer "
            "son parcours.",
        )
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST" and request.POST.get("action") == "deplacer":
        scolarite = get_object_or_404(
            Scolarite,
            eleve__pk=request.POST.get("eleve"),
            eleve__ecole=ecole,
            classe=classe,
        )
        destination = get_object_or_404(
            Classe,
            pk=request.POST.get("classe_destination"),
            ecole=ecole,
            annee_scolaire=classe.annee_scolaire,
        )
        if destination.pk == classe.pk:
            messages.error(request, "Choisissez une autre classe que celle-ci.")
        else:
            scolarite.classe = destination
            scolarite.save(update_fields=["classe", "modifie_le"])
            messages.success(
                request,
                f"{scolarite.eleve.prenom} a été déplacé vers {destination}.",
            )
        return redirect("importer_eleves", pk=classe.pk)

    if request.method == "POST" and not action:
        niveau_defaut = request.POST.get("niveau", niveau_defaut_page)
        lignes = []
        for ligne in request.POST.get("liste", "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            parts = [p.strip() for p in ligne.replace("\t", ";").split(";")]
            prenom = parts[0]
            nom = parts[1] if len(parts) > 1 else ""
            niveau = (
                parts[2].upper()
                if len(parts) > 2 and parts[2].upper() in NIVEAUX_VALIDES
                else niveau_defaut
            )
            annee_naissance = None
            if len(parts) > 3 and parts[3].isdigit():
                annee_naissance = int(parts[3])
            lignes.append(
                {
                    "prenom": prenom,
                    "nom": nom,
                    "niveau": niveau,
                    "annee_naissance": annee_naissance,
                }
            )
        resultat = importer_nouveaux_eleves(
            utilisateur=request.user,
            classe=classe,
            lignes=lignes,
            niveau_defaut=niveau_defaut,
        )
        messages.success(
            request,
            f"{resultat['crees']} enfant(s) ajouté(s) à {classe}. "
            f"{resultat['demandes']} rapprochement(s) à valider par la direction.",
        )
        return redirect("classe_detail", pk=classe.pk)

    annee_precedente = _annee_precedente(classe.annee_scolaire)
    scolarites_annee = Scolarite.objects.filter(
        eleve__ecole=ecole,
        eleve__archive_le__isnull=True,
        annee_scolaire=classe.annee_scolaire,
    ).select_related("eleve", "classe")
    ids_affectes = scolarites_annee.values_list("eleve_id", flat=True)

    eleves_disponibles = list(
        ecole.eleves.filter(archive_le__isnull=True).exclude(pk__in=ids_affectes)
    ) if direction else []
    eleves_archives = (
        list(ecole.eleves.filter(archive_le__isnull=False)) if direction else []
    )
    niveaux_annee_precedente = dict(
        Scolarite.objects.filter(
            eleve__in=eleves_disponibles + eleves_archives,
            annee_scolaire=annee_precedente,
        ).values_list("eleve_id", "niveau")
    )
    for eleve in eleves_disponibles + eleves_archives:
        eleve.niveau_suggere = NIVEAU_SUIVANT.get(
            niveaux_annee_precedente.get(eleve.pk)
        )

    affectations_autres = (
        scolarites_annee.exclude(classe=classe)
        if direction
        else Scolarite.objects.none()
    )
    composition = (
        Scolarite.objects.filter(classe=classe, eleve__archive_le__isnull=True)
        .select_related("eleve")
        .order_by("eleve__prenom", "eleve__nom")
    )
    autres_classes_annee = Classe.objects.filter(
        ecole=ecole, annee_scolaire=classe.annee_scolaire
    ).exclude(pk=classe.pk) if direction else Classe.objects.none()
    demandes = []
    if direction:
        for demande in DemandeRapprochementEleve.objects.filter(
            classe=classe, etat=DemandeRapprochementEleve.EN_ATTENTE
        ):
            demande.candidats = correspondances(
                ecole,
                demande.prenom_propose,
                demande.nom_propose,
                demande.annee_naissance_proposee,
            )
            demandes.append(demande)
    return render(
        request,
        "suivi/importer_eleves.html",
        {
            "classe": classe,
            "niveau_defaut_page": niveau_defaut_page,
            "composition": composition,
            "autres_classes_annee": autres_classes_annee,
            "eleves_disponibles": eleves_disponibles,
            "affectations_autres": affectations_autres,
            "eleves_archives": eleves_archives,
            "direction": direction,
            "demandes_rapprochement": demandes,
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
    eleve = charger_eleve_autorise(request.user, pk, VOIR_SUIVI, ecole=ecole)
    responsable = autorise(request.user, MODIFIER_ETAT, eleve, ecole=ecole)
    scolarites_visibles, scolarite_courante = _scolarites_visibles(
        request.user, eleve
    )
    scolarites = scolarites_visibles.filter(pk=scolarite_courante.pk).select_related(
        "classe"
    )
    bilans = list(
        Bilan.objects.filter(
            Q(scolarite=scolarite_courante)
            | Q(
                scolarite__in=scolarites_visibles.exclude(pk=scolarite_courante.pk),
                visible_carnet=True,
            ),
            supprime_le__isnull=True,
        ).select_related("scolarite")
    )
    for bilan in bilans:
        bilan.peut_modifier = responsable and (
            bilan.scolarite_id == scolarite_courante.pk
        )
    bilan_obj = None
    if bilan_pk is not None:
        bilan_obj = get_object_or_404(
            Bilan,
            pk=bilan_pk,
            scolarite__eleve=eleve,
            scolarite=scolarite_courante,
            supprime_le__isnull=True,
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
                        "bilans": bilans,
                        "bilan_obj": bilan_en_conflit,
                        "date_defaut": timezone.localdate(),
                        "responsable": responsable,
                    },
                )
            bilan_obj = enregistrer_bilan(
                utilisateur=request.user,
                bilan=bilan_obj,
                valeurs={
                    "scolarite": scolarite,
                    "date_bilan": date_bilan,
                    "texte": texte,
                    "visible_carnet": request.POST.get("visible_carnet") == "on",
                },
            )
            messages.success(request, "Quelques mots sur le parcours enregistrés.")
            return redirect("bilans_eleve", pk=eleve.pk)
        messages.error(request, "La date et le texte sont obligatoires.")
    return render(
        request,
        "suivi/bilans.html",
        {
            "eleve": eleve,
            "scolarites": scolarites,
            "bilans": bilans,
            "bilan_obj": bilan_obj,
            "date_defaut": timezone.localdate(),
            "responsable": responsable,
        },
    )


@acces_requis
def supprimer_bilan(request, pk, bilan_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(request.user, pk, MODIFIER_ETAT, ecole=ecole)
    bilan = get_object_or_404(
        Bilan,
        pk=bilan_pk,
        scolarite__eleve=eleve,
        scolarite=eleve.scolarite_courante(),
        supprime_le__isnull=True,
    )
    supprimer_bilan_logiquement(utilisateur=request.user, bilan=bilan)
    messages.success(request, "Bilan supprimé.")
    return redirect("bilans_eleve", pk=eleve.pk)


@acces_requis
def basculer_visibilite_bilan(request, pk, bilan_pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(request.user, pk, MODIFIER_ETAT, ecole=ecole)
    bilan = get_object_or_404(
        Bilan,
        pk=bilan_pk,
        scolarite__eleve=eleve,
        scolarite=eleve.scolarite_courante(),
        supprime_le__isnull=True,
    )
    definir_visibilite_bilan(
        utilisateur=request.user,
        bilan=bilan,
        visible=not bilan.visible_carnet,
    )
    etat = "affiché dans le carnet" if bilan.visible_carnet else "masqué du carnet"
    messages.success(request, f"Bilan {etat}.")
    return redirect("bilans_eleve", pk=eleve.pk)


@acces_requis
def archiver_eleve(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    classe = eleve.classe
    if classe is None and not est_direction(request.user, eleve.ecole):
        raise Http404
    archiver(utilisateur=request.user, eleve=eleve, classe=classe)
    messages.success(request, f"{eleve.prenom} a été archivé sans supprimer son parcours.")
    return redirect("gestion")


@acces_requis
def desarchiver_eleve(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    eleve = get_object_or_404(Eleve, pk=pk, ecole=ecole_courante(request))
    classe = eleve.classe
    if classe is None and not est_direction(request.user, eleve.ecole):
        raise Http404
    desarchiver(utilisateur=request.user, eleve=eleve, classe=classe)
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
