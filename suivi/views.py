from functools import wraps
import tempfile
import logging
import mimetypes
from pathlib import Path
import re
import shutil
import sys
import traceback
from datetime import datetime
import sqlite3
from io import BytesIO
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from collections import OrderedDict
from urllib.parse import quote, unquote, urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from carnet.reseau import adresse_client, cle_ip
from comptes import totp
from pas_communs.authentification import sessions as mecanismes_sessions
from comptes.validators import LONGUEUR_MAX_MOT_DE_PASSE
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.db.models import F, Max, Count, Prefetch, Q
from django.http import (
    QueryDict,
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe, require_http_methods

from comptes.models import (
    AffectationClasse,
    AppartenanceEcole,
    DoubleFacteurCompte,
    Invitation,
    ResponsabiliteEcole,
    Utilisateur,
)
from comptes.forms import (
    CreationCompteInvitationForm, DernierRecoursForm, InstallationLocaleForm, ProfilForm,
    ReinitialisationParCleForm,
)
from comptes import secours_local
from .services import acces_local
from .forms import DroitsGestionForm
from .confirmations_referentiels import verifier_confirmation
from .lectures_eleves import avec_scolarites_pour_lecture

from .acces_double_facteur import (
    DELAI_ATTENTE_SECONDES, SESSION_ATTENTE, SESSION_VERIFIE,
    connexion_recente, noter_authentification, verification_requise_a_la_connexion,
)
from .double_facteur import Exigence, exigence_double_facteur
from .services.double_facteur import (
    journaliser_securite_compte, refus_reinitialisation, reinitialiser_par_la_direction,
)
from .navigation import (
    chemin_classe, chemin_collectif, chemin_competence, filtre_competences, lien,
)
from .autorisations import (
    ACCEDER_APPLICATION,
    ADMINISTRER_ECOLE,
    GERER_REFERENTIEL_CLASSE,
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
    appartenances_actives,
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
    RessourceReferentiel,
    DemandeRapprochementEleve,
    Domaine,
    Ecole,
    Eleve,
    Observation,
    ParametresCarnet,
    ReglagePresentation,
    Scolarite,
    Trace,
    TraceCommune,
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
from .services.traces_communes import enregistrer_commune, personnaliser, personnaliser_texte, supprimer_commune
from .services.medias_django import preparer_image
from .presentation import (affichage_avec_photos, credit_illustration, CREDITS_IMAGES,
                           illustration_effective, reglages_du_perimetre, formulations_effectives)
from .correspondances_referentiels import correspondances_classe
from .referentiels import arbre_competences as _arbre, adoption_courante, observations_annee, competence_classe, observations_classe, projeter_etat_classe, classe_historique, competence_saisissable
from .services.equipe import (
    accepter_invitation,
    activer_classe,
    attribuer_affectation,
    attribuer_direction,
    terminer_direction,
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


def is_ratelimited(request, **options):
    if settings.MODE_LOCAL and not settings.ANTIBRUTEFORCE_ACTIF:
        return False
    from django_ratelimit.core import is_ratelimited as verifier_limite
    return verifier_limite(request, **options)


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


def _tracer_echec_connexion(request, nom_utilisateur):
    """Trace minimale d'un échec d'authentification (jamais le mot de passe).

    django-axes conserve le détail des tentatives quand il est actif ; cette
    ligne garantit une trace dans les journaux du serveur dans tous les cas.
    %r neutralise les retours à la ligne éventuels de l'identifiant saisi."""
    logger.warning(
        "Échec de connexion pour %r depuis %s",
        nom_utilisateur,
        adresse_client(request) or "?",
    )


def _signaler_reinitialisations(request, utilisateur, depuis):
    """Rappelle, à la connexion, les mots de passe réinitialisés depuis l'appareil."""
    for evenement in acces_local.reinitialisations_a_signaler(utilisateur, depuis):
        quand = timezone.localtime(evenement["quand"]).strftime("%d/%m/%Y à %Hh%M")
        sujet = "Votre mot de passe a" if evenement["moi"] else f"Le mot de passe de {evenement['nom']} a"
        messages.warning(request, f"{sujet} été réinitialisé depuis cet appareil le {quand}.")


def _suite_connexion(request, utilisateur, nom_utilisateur):
    """Après une connexion réussie (second facteur compris) : choix de la page
    d'arrivée, ou refus si le compte n'a encore aucune fonction."""
    ecole = ecole_courante(request)
    if ecole and autorise(utilisateur, ACCEDER_APPLICATION, ecole=ecole):
        if (settings.MODE_LOCAL and est_direction(utilisateur, ecole)
                and lire_resultat(Path(settings.DATABASES["default"]["NAME"]).parent)):
            request.session.pop("suivant", None)
            return redirect("sauvegardes_locales")
        return redirect(request.session.pop("suivant", None) or "accueil")
    membre_sans_fonction = appartenances_actives(utilisateur).exists()
    logout(request)
    if membre_sans_fonction:
        messages.warning(
            request,
            "Votre compte existe, mais aucune fonction ne vous a "
            "encore été attribuée dans une classe. Contactez la "
            "direction de votre école.",
        )
    else:
        messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
    return render(
        request, "suivi/connexion.html", {"nom_utilisateur": nom_utilisateur}
    )


def connexion(request):
    if settings.MODE_LOCAL and not Ecole.objects.exists() and not Utilisateur.objects.exists():
        return redirect("installation_locale")
    if request.user.is_authenticated:
        return redirect("accueil")
    if request.method == "POST":
        if settings.ANTIBRUTEFORCE_ACTIF and is_ratelimited(
                request, group="connexion_ip", key=cle_ip,
                rate=settings.RATELIMIT_CONNEXION_IP, method="POST", increment=False):
            return render(request, "suivi/connexion_bloquee.html", status=429)
        nom_utilisateur = request.POST.get("nom_utilisateur", "").strip()
        utilisateur = authenticate(
            request,
            username=nom_utilisateur,
            password=request.POST.get("mot_de_passe", ""),
        )
        if utilisateur:
            if verification_requise_a_la_connexion(utilisateur):
                # Aucune session n'est ouverte avant le second facteur.
                mecanismes_sessions.commencer_attente(request.session, utilisateur,
                    cle=SESSION_ATTENTE, delai=DELAI_ATTENTE_SECONDES)
                return redirect("connexion_verification")
            precedente_connexion = utilisateur.last_login
            login(request, utilisateur)
            _signaler_reinitialisations(request, utilisateur, precedente_connexion)
            return _suite_connexion(request, utilisateur, nom_utilisateur)
        _tracer_echec_connexion(request, nom_utilisateur)
        if settings.ANTIBRUTEFORCE_ACTIF:
            is_ratelimited(
                request, group="connexion_ip", key=cle_ip,
                rate=settings.RATELIMIT_CONNEXION_IP, method="POST", increment=True)
        messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
        return render(
            request, "suivi/connexion.html", {"nom_utilisateur": nom_utilisateur}
        )
    request.session.pop(SESSION_ATTENTE, None)
    return render(request, "suivi/connexion.html")


def _compte_en_attente(request):
    return mecanismes_sessions.compte_en_attente(request.session,
        cle=SESSION_ATTENTE, delai=DELAI_ATTENTE_SECONDES)


def _cle_compte_double_facteur(groupe, request):
    return f"compte-{request.session[SESSION_ATTENTE]['pk']}"


def _trop_de_tentatives_double_facteur(request):
    """Plafonne les saisies de code, par compte puis par adresse : elles ne
    passent pas par authenticate(), donc django-axes ne les voit pas."""
    return is_ratelimited(
        request, group="double_facteur_compte", key=_cle_compte_double_facteur,
        rate=settings.RATELIMIT_DOUBLE_FACTEUR, method="POST", increment=True,
    ) | is_ratelimited(
        request, group="double_facteur_ip", key=cle_ip,
        rate=settings.RATELIMIT_DOUBLE_FACTEUR_IP, method="POST", increment=True,
    )


@never_cache
def connexion_verification(request):
    utilisateur, attente = _compte_en_attente(request)
    if utilisateur is None:
        return redirect("connexion")
    if request.method == "POST":
        if _trop_de_tentatives_double_facteur(request):
            request.session.pop(SESSION_ATTENTE, None)
            return render(request, "suivi/connexion_verification.html",
                          {"trop_de_tentatives": True}, status=429)
        saisie = request.POST.get("code", "")
        secours = False
        verifie = totp.verifier_code(utilisateur, saisie)
        if not verifie and totp.normaliser_code_secours(saisie):
            verifie = secours = totp.utiliser_code_secours(utilisateur, saisie)
        if verifie:
            request.session.pop(SESSION_ATTENTE, None)
            login(request, utilisateur, backend=attente["backend"])
            request.session[SESSION_VERIFIE] = True
            if secours:
                journaliser_securite_compte(utilisateur, utilisateur, "securite.code_secours_utilise")
                restants = totp.codes_secours_restants(utilisateur)
                messages.warning(
                    request,
                    f"Un code de secours a été utilisé. Il vous en reste {restants}."
                    + (" Générez-en de nouveaux depuis « Mon compte »." if restants <= 2 else ""),
                )
            return _suite_connexion(request, utilisateur, utilisateur.get_username())
        logger.warning(
            "Échec du second facteur pour le compte %s depuis %s",
            utilisateur.pk, adresse_client(request) or "?",
        )
        messages.error(request, "Code incorrect ou expiré.")
    return render(request, "suivi/connexion_verification.html")


@never_cache
@acces_requis
def double_facteur(request):
    """Inscription au second facteur, état et retrait volontaire."""
    if not settings.DOUBLE_FACTEUR_DISPONIBLE:
        raise Http404
    exigence = exigence_double_facteur(request.user)
    inscrit = totp.est_inscrit(request.user)
    if exigence == Exigence.DESACTIVEE and not inscrit:
        raise Http404
    contexte = {"inscrit": inscrit, "obligatoire": exigence == Exigence.OBLIGATOIRE}
    if inscrit:
        contexte["codes_restants"] = totp.codes_secours_restants(request.user)
    if request.method == "POST":
        if _trop_de_tentatives_double_facteur_connecte(request):
            return render(request, "suivi/double_facteur.html",
                          {**contexte, "trop_de_tentatives": True}, status=429)
        code = request.POST.get("code", "")
        if inscrit and request.POST.get("action") == "regenerer_codes":
            if totp.verifier_code(request.user, code):
                codes = totp.generer_codes_secours(request.user)
                journaliser_securite_compte(request.user, request.user, "securite.codes_secours_regeneres")
                return render(request, "suivi/double_facteur.html",
                              {**contexte, "codes_secours": codes, "codes_restants": len(codes)})
            messages.error(request, "Code incorrect ou expiré.")
        elif inscrit and request.POST.get("action") == "retirer":
            if exigence == Exigence.OBLIGATOIRE:
                messages.error(request, "Le second facteur est obligatoire pour votre fonction.")
            elif totp.verifier_code(request.user, code):
                totp.retirer(request.user)
                request.session.pop(SESSION_VERIFIE, None)
                messages.success(request, "Le second facteur a été retiré.")
                return redirect("mon_compte")
            else:
                messages.error(request, "Code incorrect ou expiré.")
        elif not inscrit:
            saisie = request.POST.get("mot_de_passe", "")
            if not connexion_recente(request) and not (
                    len(saisie) <= LONGUEUR_MAX_MOT_DE_PASSE
                    and request.user.check_password(saisie)):
                messages.error(
                    request, "Confirmez votre mot de passe pour configurer le second facteur.")
            elif totp.confirmer_inscription(request.user, code):
                request.session[SESSION_VERIFIE] = True
                noter_authentification(request)
                codes = totp.generer_codes_secours(request.user)
                # Affichés une seule fois, dans cette réponse : jamais conservés en clair.
                return render(request, "suivi/double_facteur.html",
                              {"inscrit": True, "obligatoire": exigence == Exigence.OBLIGATOIRE,
                               "codes_secours": codes, "codes_restants": len(codes),
                               "inscription_terminee": True})
            else:
                messages.error(request, "Code incorrect ou expiré. Vérifiez l'heure de l'appareil qui produit les codes.")
    if not inscrit:
        contexte["mot_de_passe_requis"] = not connexion_recente(request)
        compte = totp.commencer_inscription(request.user)
        cle = totp.cle_en_cours(compte)
        contexte.update({
            "qr_svg": totp.qr_svg(totp.uri_otpauth(request.user, cle)),
            "cle_saisie": " ".join(totp.cle_en_base32(cle)[i:i + 4] for i in range(0, 32, 4)),
        })
    return render(request, "suivi/double_facteur.html", contexte)


def _trop_de_tentatives_double_facteur_connecte(request):
    return is_ratelimited(
        request, group="double_facteur_compte", key=lambda g, r: f"compte-{r.user.pk}",
        rate=settings.RATELIMIT_DOUBLE_FACTEUR, method="POST", increment=True,
    ) | is_ratelimited(
        request, group="double_facteur_ip", key=cle_ip,
        rate=settings.RATELIMIT_DOUBLE_FACTEUR_IP, method="POST", increment=True,
    )


@never_cache
def verifier_zip_local(request):
    if not settings.MODE_LOCAL or settings.ESPACE_APERCU:
        raise Http404
    from . import apercu_local
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if restauration_en_attente() is not None or preparation_en_attente() is not None:
                raise ValueError("Terminez ou annulez la restauration en cours avant d'ouvrir une copie.")
            if action == "annuler":
                apercu_local.annuler()
            elif action == "ouvrir":
                apercu_local.demander_ouverture()
            elif action == "installer_vide":
                if Ecole.objects.exists() or Utilisateur.objects.exists():
                    raise ValueError("Une école ou un compte existe déjà. Utilisez la restauration avec un compte de direction.")
                copie = apercu_local.preparation()
                if copie is None:
                    raise ValueError("Vérifiez d’abord un ZIP.")
                (copie.etape / apercu_local.MARQUEUR).unlink()
                retenir_preparation(copie)
                apercu_local.detacher()
                confirmer_restauration()
            elif action == "verifier":
                archive = request.FILES.get("archive")
                if not archive:
                    raise ValueError("Choisissez un fichier ZIP Petits Pas.")
                from django.db.migrations.loader import MigrationLoader
                limites = {"migrations_connues": MigrationLoader(None).disk_migrations}
                if getattr(settings, "MODE_PWA", False):
                    limites.update(taille_max=64 * 1024**2, fichiers_max=5000)
                else:
                    limites["controler_disque"] = True
                paquet = Path(settings.DATABASES["default"]["NAME"]).parent
                apercu_local.preparer(archive, paquet.parent, **limites)
        except (ValueError, OSError, RuntimeError, KeyError, BadZipFile, sqlite3.DatabaseError) as erreur:
            messages.error(request, f"Copie refusée : {erreur}")
    paquet = Path(settings.DATABASES["default"]["NAME"]).parent
    derniere = None if getattr(settings, "MODE_PWA", False) else apercu_local.derniere_copie(paquet.parent, paquet, paquet.parent / "essai-fictif")
    return render(request, "suivi/verifier_zip_local.html", {
        "copie": apercu_local.preparation(), "ouverture_demandee": apercu_local.ouverture_demandee(),
        "derniere_copie": derniere, "installation_vide": not Ecole.objects.exists() and not Utilisateur.objects.exists(),
        "restauration_attente": restauration_en_attente() is not None})


@never_cache
def choisir_espace_local(request):
    if not settings.MODE_LOCAL or getattr(settings, "MODE_PWA", False):
        raise Http404
    import json
    try:
        identifiants = json.loads((settings.BASE_DIR / "referentiel/demo/ecole-fictive.json").read_text())["identifiants"]
    except (OSError, ValueError, KeyError):
        identifiants = None
    return render(request, "suivi/choisir_espace_local.html",
                  {"destination": "habituel" if settings.ESPACE_ESSAI or settings.ESPACE_APERCU else "essai",
                   "identifiants": identifiants})


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
        try:
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
                from .services.installation_locale import preparer_referentiel, preparer_premiere_classe
                version = preparer_referentiel(utilisateur=utilisateur, ecole=ecole,
                    annee=formulaire.cleaned_data["annee_scolaire"], choix=formulaire.cleaned_data["referentiel"])
                classe = None
                if formulaire.cleaned_data["preparer_classe"]:
                    classe = Classe.objects.create(ecole=ecole,
                        nom=formulaire.cleaned_data["classe_nom"],
                        annee_scolaire=formulaire.cleaned_data["annee_scolaire"])
                    preparer_premiere_classe(utilisateur=utilisateur, appartenance=appartenance,
                                             classe=classe, version=version,
                                             selection_manuelle=formulaire.cleaned_data["selection_manuelle"])
                cle_secours = None
                if acces_local.disponible():
                    acces_local.definir_dernier_recours(
                        acteur=utilisateur, ecole=ecole,
                        autorise_recours=formulaire.cleaned_data["dernier_recours"])
                    cle_secours = acces_local.generer_cle(utilisateur)
        except ValidationError as erreur:
            formulaire.add_error(None, erreur)
            return render(request, "suivi/installation_locale.html", {"formulaire": formulaire})
        login(request, utilisateur, backend="django.contrib.auth.backends.ModelBackend")
        request.session["ecole_id"] = ecole.pk
        request.session.pop("suivant", None)
        if classe:
            messages.success(request, "École et classe créées. Vous pouvez ajouter les élèves.")
            suite = reverse("importer_eleves", args=[classe.pk])
        else:
            messages.success(request, "École créée. Vous pouvez maintenant préparer une classe.")
            suite = reverse("gestion")
        if cle_secours:
            _remettre_cle_secours(request, cle_secours, suite=suite,
                                  preuve=not formulaire.cleaned_data["dernier_recours"])
            return redirect("cle_secours")
        return redirect(suite)
    return render(request, "suivi/installation_locale.html", {"formulaire": formulaire})


@never_cache
@acces_requis
def acces_local_ecole(request):
    """Autoriser ou non le dernier recours ; la direction seule, en étant connectée."""
    if not acces_local.disponible():
        raise Http404
    ecole = ecole_courante(request)
    if not autorise(request.user, ADMINISTRER_ECOLE, ecole=ecole):
        raise PermissionDenied
    autorise_actuellement = acces_local.dernier_recours_autorise(ecole)
    a_une_cle = secours_local.possede_une_cle(request.user)
    erreur = None
    if request.method == "POST":
        voulu = request.POST.get("dernier_recours") == "on"
        if autorise_actuellement and not voulu and not secours_local.cle_correspond(
                request.user, request.POST.get("cle", "")):
            erreur = ("Pour interdire le dernier recours, recopiez votre clé de secours : "
                      "elle devient alors votre seule issue en cas d’oubli.")
        else:
            acces_local.definir_dernier_recours(
                acteur=request.user, ecole=ecole, autorise_recours=voulu)
            messages.success(request, "Le dernier recours est autorisé." if voulu
                             else "Le dernier recours n’est plus autorisé.")
            return redirect("gestion")
    return render(request, "suivi/acces_local_ecole.html", {
        "autorise_actuellement": autorise_actuellement, "a_une_cle": a_une_cle,
        "erreur": erreur})


@never_cache
@acces_requis
def mise_a_niveau_acces(request):
    """Une fois, pour la direction d'une installation existante : clé et dernier recours."""
    if not acces_local.disponible():
        raise Http404
    ecole = ecole_courante(request)
    if not acces_local.mise_a_niveau_a_proposer(request.user, ecole, request.session):
        return redirect("accueil")
    a_une_cle = secours_local.possede_une_cle(request.user)
    erreur = None
    if request.method == "POST":
        if request.POST.get("action") == "plus_tard":
            request.session[acces_local.SESSION_PLUS_TARD] = True
            return redirect("accueil")
        voulu = request.POST.get("dernier_recours") == "on"
        if a_une_cle and not voulu and not secours_local.cle_correspond(
                request.user, request.POST.get("cle", "")):
            erreur = ("Pour ne pas autoriser le dernier recours, recopiez votre clé de secours : "
                      "elle devient alors votre seule issue en cas d’oubli.")
        else:
            acces_local.definir_dernier_recours(
                acteur=request.user, ecole=ecole, autorise_recours=voulu)
            if not a_une_cle:
                _remettre_cle_secours(request, acces_local.generer_cle(request.user),
                                      suite=reverse("accueil"), preuve=not voulu)
                return redirect("cle_secours")
            messages.success(request, "C’est enregistré.")
            return redirect("accueil")
    return render(request, "suivi/mise_a_niveau_acces.html", {
        "a_une_cle": a_une_cle, "erreur": erreur})


SESSION_CLE_SECOURS = "cle_secours_a_montrer"


def _remettre_cle_secours(request, cle, *, suite, preuve):
    """Garde la clé le temps de la montrer une fois ; elle n'est jamais relue ensuite."""
    request.session[SESSION_CLE_SECOURS] = {"cle": cle, "suite": suite, "preuve": preuve}


@never_cache
@acces_requis
def cle_secours(request):
    """Montre la clé de secours une seule fois, puis poursuit le parcours."""
    if not acces_local.disponible():
        raise Http404
    en_attente = request.session.get(SESSION_CLE_SECOURS)
    if not en_attente:
        return redirect("mon_compte")
    erreur = None
    if request.method == "POST":
        fin = "".join(c for c in request.POST.get("fin_de_cle", "").upper() if c not in " -")
        attendue = en_attente["cle"].replace("-", "")[-8:]
        if en_attente["preuve"] and fin != attendue:
            erreur = ("Ces signes ne correspondent pas à la fin de votre clé. "
                      "Relisez-la ci-dessus et recopiez ses deux derniers groupes.")
        else:
            request.session.pop(SESSION_CLE_SECOURS, None)
            return redirect(en_attente["suite"])
    return render(request, "suivi/cle_secours.html", {
        "cle": en_attente["cle"], "preuve": en_attente["preuve"], "erreur": erreur,
        "saisie": request.POST.get("fin_de_cle", ""),
    })


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
        if action == "sauvegarder":
            fichier = tempfile.TemporaryFile(dir=paquet.parent)
            try:
                creer_sauvegarde(paquet, fichier)
                from .paquet_local import noter_export
                noter_export(paquet)
                fichier.seek(0)
                return FileResponse(
                    fichier, as_attachment=True,
                    filename=f"petits-pas-{timezone.now():%Y%m%d-%H%M%S}.zip",
                    content_type="application/zip",
                )
            except Exception:
                fichier.close()
                raise
        if preparation_en_attente() is not None:
            return redirect("sauvegardes_locales")
        if request.POST.get("action") == "restaurer":
            if settings.ESPACE_APERCU:
                messages.error(request, "Pour ouvrir un autre ZIP, revenez d’abord à l’école habituelle.")
                return redirect("sauvegardes_locales")
            archive = request.FILES.get("archive")
            if not archive:
                messages.error(request, "Choisissez un fichier de sauvegarde.")
            else:
                try:
                    from django.db.migrations.loader import MigrationLoader
                    limites = {"migrations_connues": MigrationLoader(None).disk_migrations}
                    if getattr(settings, "MODE_PWA", False):
                        limites.update(taille_max=64 * 1024**2, fichiers_max=5000)
                    else:
                        limites["controler_disque"] = True
                    etape = preparer_restauration(archive, paquet.parent, paquet.name, **limites)
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
    from .paquet_local import suivi_export
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
            **suivi_export(paquet),
            "restauration_attente": restauration_en_attente() is not None,
            "preparation": preparation,
            "paquet": paquet,
            "date_sauvegarde": date_affichee(preparation.date_sauvegarde) if preparation else None,
            "resultat": resultat,
            "date_resultat": date_affichee(resultat["date_sauvegarde"]) if resultat else None,
            "date_application": date_affichee(resultat["applique_le"]) if resultat else None,
        },
    )


def _ouvrir_session_locale(request, compte, ecole):
    login(request, compte, backend="django.contrib.auth.backends.ModelBackend")
    if ecole:
        request.session["ecole_id"] = ecole.pk


def _mot_de_passe_oublie_local(request):
    """Sans courriel : la clé de secours, puis le dernier recours si l'école l'autorise."""
    ecole = acces_local.ecole_locale()
    formulaire = ReinitialisationParCleForm(request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        try:
            nouvelle_cle = acces_local.reinitialiser_par_cle(
                formulaire.compte_cible, formulaire.cleaned_data["new_password1"])
        except ValidationError as erreur:
            formulaire.add_error("new_password1", erreur)
        else:
            _ouvrir_session_locale(request, formulaire.compte_cible, ecole)
            messages.success(request, "Votre nouveau mot de passe est enregistré.")
            _remettre_cle_secours(request, nouvelle_cle, suite=reverse("accueil"), preuve=False)
            return redirect("cle_secours")
    return render(request, "suivi/mot_de_passe_oublie.html", {
        "local": True, "formulaire": formulaire,
        "dernier_recours": acces_local.dernier_recours_autorise(ecole)})


@never_cache
def dernier_recours(request):
    """Nouveau mot de passe depuis l'appareil, quand l'école l'a autorisé."""
    if not acces_local.disponible():
        raise Http404
    ecole = acces_local.ecole_locale()
    if not acces_local.dernier_recours_autorise(ecole):
        messages.info(request, "Le dernier recours n’est pas autorisé sur cet appareil.")
        return redirect("mot_de_passe_oublie")
    formulaire = DernierRecoursForm(
        request.POST or None, comptes=acces_local.comptes_reinitialisables(ecole))
    if request.method == "POST" and formulaire.is_valid():
        compte = formulaire.compte_cible
        try:
            acces_local.reinitialiser_dernier_recours(
                compte, formulaire.cleaned_data["new_password1"], ecole)
        except ValidationError as erreur:
            formulaire.add_error("new_password1", erreur)
        else:
            _ouvrir_session_locale(request, compte, ecole)
            messages.success(
                request, "Votre nouveau mot de passe est enregistré. Vos données sont intactes.")
            return redirect("accueil")
    return render(request, "suivi/dernier_recours.html", {"formulaire": formulaire})


def mot_de_passe_oublie(request):
    if acces_local.disponible():
        return _mot_de_passe_oublie_local(request)
    if not settings.EMAIL_DISPONIBLE:
        return render(request, "suivi/mot_de_passe_oublie.html")
    if request.method == "POST" and is_ratelimited(
        request,
        group="mot_de_passe_oublie",
        key=cle_ip,
        rate=settings.RATELIMIT_MOT_DE_PASSE_OUBLIE,
        method="POST",
        increment=True,
    ):
        return render(
            request, "suivi/mot_de_passe_oublie.html", {"trop_de_demandes": True}
        )
    return auth_views.PasswordResetView.as_view(
        template_name="suivi/mot_de_passe_oublie.html",
        email_template_name="suivi/emails/mot_de_passe_reinitialisation.txt",
        subject_template_name=(
            "suivi/emails/mot_de_passe_reinitialisation_objet.txt"
        ),
        success_url=reverse_lazy("mot_de_passe_oublie_envoye"),
    )(request)


class _ChangementMotDePasseView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "suivi/mot_de_passe_changer.html"
    success_url = reverse_lazy("mon_compte")
    success_message = "Votre mot de passe a été modifié."


@acces_requis
def changer_mot_de_passe(request):
    # PasswordChangeView renouvelle le hachage de session après le
    # changement (update_session_auth_hash) : la personne reste connectée,
    # mais ses autres sessions ouvertes sont invalidées.
    if request.method == "POST" and is_ratelimited(
        request,
        group="changer_mot_de_passe",
        key="user",
        rate=settings.RATELIMIT_CHANGEMENT_MOT_DE_PASSE,
        method="POST",
        increment=True,
    ):
        return render(
            request,
            "suivi/mot_de_passe_changer.html",
            {"trop_de_tentatives": True},
            status=429,
        )
    return _ChangementMotDePasseView.as_view()(request)


def deconnexion(request):
    logout(request)
    return redirect("connexion")


@acces_requis
def mon_compte(request):
    if request.method == "POST" and request.POST.get("action") == "nouvelle_cle_secours":
        if not acces_local.disponible():
            raise Http404
        _remettre_cle_secours(request, acces_local.generer_cle(request.user),
                              suite=reverse("mon_compte"), preuve=False)
        return redirect("cle_secours")
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
    double_facteur_propose = False
    if settings.DOUBLE_FACTEUR_DISPONIBLE:
        double_facteur_propose = (
            totp.est_inscrit(request.user)
            or exigence_double_facteur(request.user) != Exigence.DESACTIVEE
        )
    return render(
        request,
        "suivi/mon_compte.html",
        {"formulaire": formulaire, "affectations": affectations,
         "double_facteur_propose": double_facteur_propose,
         "double_facteur_inscrit": double_facteur_propose and totp.est_inscrit(request.user),
         "a_une_cle": acces_local.disponible() and secours_local.possede_une_cle(request.user),
         "dernier_recours_autorise": acces_local.dernier_recours_autorise()},
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
            nom_utilisateur = request.POST.get("nom_utilisateur", "").strip()
            utilisateur = authenticate(
                request,
                username=nom_utilisateur,
                password=request.POST.get("mot_de_passe", ""),
            )
            if not utilisateur:
                _tracer_echec_connexion(request, nom_utilisateur)
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
                        {
                            "invitation": invitation,
                            "acceptee": True,
                            "fonctions_preattribuees": list(
                                invitation.affectations_classes.filter(
                                    appartenance__utilisateur=utilisateur, etat=AffectationClasse.ACTIVE,
                                ).select_related("classe", "appartenance")
                            ),
                        },
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
                    {
                        "invitation": invitation,
                        "acceptee": True,
                        "fonctions_preattribuees": list(
                            invitation.affectations_classes.filter(
                                appartenance__isnull=False, etat=AffectationClasse.ACTIVE,
                            ).select_related("classe", "appartenance")
                        ),
                    },
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
    from .services.garde_fous_referentiels import demarrage_ecole
    ecole = ecole_courante(request)
    if (settings.MODE_LOCAL and est_direction(request.user, ecole)
            and lire_resultat(Path(settings.DATABASES["default"]["NAME"]).parent)):
        return redirect("sauvegardes_locales")
    if acces_local.mise_a_niveau_a_proposer(request.user, ecole, request.session):
        return redirect("mise_a_niveau_acces")
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
            "demarrage_ecole": est_direction(request.user, ecole) and demarrage_ecole(ecole),
            "groupes": groupes,
            "toutes": toutes,
            "a_des_annees_passees": a_des_annees_passees,
        },
    )


FILTRES_NIVEAU_CLASSE = {"classe", "tous", "PS", "MS", "GS"}


def _progression(eleves, ecole, filtre="classe", classe=None):
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
    competences = [c for d in _arbre(ecole, classe=classe) for c in d.visibles]
    total_cycle = len(competences)
    queryset = observations_classe(classe) if classe else Observation.objects.annotate(statut_lecture=F("statut"))
    reussies = {}
    for eid, cid in queryset.filter(eleve__pk__in=[e.pk for e in eleves],
            statut_lecture="reussi", competence_id__in=[c.pk for c in competences]).values_list("eleve_id", "competence_id"):
        reussies.setdefault(eid, set()).add(cid)
    for e in eleves:
        niveau = filtre if filtre in {"PS", "MS", "GS"} else e.niveau
        concernees = {c.pk for c in competences
            if (filtre == "tous" or c.niveau == niveau)
            and (not getattr(c, "suivi_libre", False) or e.pk in c.eleves_suivis_ids)}
        e.total_competences = len(concernees)
        e.nb_reussies = len(concernees & reussies.get(e.pk, set()))
        e.part_reussies = round(100 * e.nb_reussies / e.total_competences) if e.total_competences else 0

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
    from .exports_classe import autorise_export_classe
    eleves = list(avec_scolarites_pour_lecture(classe.eleves))
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
        total = _progression(eleves, ecole, filtre, classe=classe)
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
            "peut_gerer_referentiel": autorise(request.user, GERER_REFERENTIEL_CLASSE, classe),
            "referentiel_choisi": bool(adoption_courante(classe)),
            "peut_gerer_eleves": peut_gerer_eleves,
            "vue_minimale": vue_minimale,
            "export_classe_autorise": autorise_export_classe(request.user, classe),
        },
    )


@acces_requis
def collaborateurs_classe(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(
        request.user, pk, VOIR_AFFECTATIONS_CLASSE, ecole=ecole
    )
    # Une personne qui n'a jamais rejoint l'école (invitation révoquée,
    # expirée, pré-attribution annulée) n'est pas un collaborateur.
    affectations = classe.affectations.filter(
        Q(appartenance__isnull=False)
        | Q(
            etat=AffectationClasse.ACTIVE,
            invitation__etat=Invitation.EN_ATTENTE,
            invitation__expire_le__gte=timezone.now(),
        )
    ).select_related(
        "appartenance__utilisateur", "invitation"
    ).order_by("appartenance__utilisateur__last_name", "invitation__email", "date_debut")
    return render(
        request,
        "suivi/collaborateurs_classe.html",
        {
            "classe": classe,
            "affectations": affectations,
            # L'adresse d'une personne invitée n'est pas un renseignement
            # destiné à toute la classe : seule la direction la voit.
            "peut_voir_adresses": autorise(request.user, ADMINISTRER_ECOLE, ecole=ecole),
        },
    )


# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------


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


def _retour_grille_eleve(request):
    retour = request.GET.get("retour", "")[:4000]
    prefixe = reverse("grille_classe", args=[0]).split("/classe/0/")[0]
    if re.fullmatch(re.escape(prefixe) + r"/classe/[0-9]+/(?:competence/[0-9]+/)?grille/\?[^#]*#eleve-[0-9]+-[0-9]+", retour):
        return retour
    return ""


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
    filtre = filtre_competences(request)
    niveaux = None if filtre == "tous" else [filtre]

    etats = {o.competence_id: o for o in _observations_visibles(request.user, eleve)}
    domaines = []
    courante = eleve.scolarite_courante()
    if courante and classe_historique(courante.classe):
        visibles = set(etats)
        etats = {o.competence_id: projeter_etat_classe(o)
                 for o in observations_classe(courante.classe).filter(eleve=eleve, competence_id__in=visibles)}
    classe = courante.classe if courante else None
    from .rubriques import regrouper_rubriques_saisie, rubriques_saisissables
    arbre = regrouper_rubriques_saisie(_arbre(ecole, niveaux, classe=classe, eleve=eleve), adoption_courante(classe))
    for d in rubriques_saisissables(arbre, classe):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles]
        domaines.append((d, lignes))

    return render(
        request,
        "suivi/saisie_eleve.html",
        {"eleve": eleve, "classe": classe, "domaines": domaines, "filtre": filtre,
         "retour_grille": _retour_grille_eleve(request),
         "responsable": autorise(request.user, MODIFIER_ETAT, eleve) and not (courante and classe_historique(courante.classe))},
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
    courante = eleve.scolarite_courante()
    classe = courante.classe if courante else None
    domaines = [(d, d.visibles) for d in _arbre(ecole, classe=classe, eleve=eleve)]
    return render(
        request,
        "suivi/contribuer_eleve.html",
        {"eleve": eleve, "classe": classe, "domaines": domaines},
    )


@acces_requis
def choisir_competence(request, pk):
    from .views_catalogue import catalogue
    return catalogue(request, pk, saisie_collective=True)


@acces_requis
def saisie_competence(request, pk, competence_pk):
    """La saisie éclair : une compétence, toute la classe d'un coup."""
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    competence = competence_classe(classe, competence)
    if competence is None:
        raise Http404
    filtre = filtre_competences(request)
    saisissable = competence_saisissable(classe, competence)
    etats = {o.eleve_id: projeter_etat_classe(o)
             for o in observations_classe(classe).filter(competence=competence).prefetch_related("traces")}
    eleves = list(avec_scolarites_pour_lecture(
        classe.eleves.annotate(derniere_annee=Max("scolarites__annee_scolaire"))))
    for eleve in eleves:
        eleve.hors_suivi = competence.suivi_libre and eleve.pk not in competence.eleves_suivis_ids
        eleve.peut_saisir_dans_classe = eleve.derniere_annee == classe.annee_scolaire and not eleve.hors_suivi
    lignes = [(e, etats.get(e.pk)) for e in eleves]
    from .navigation import retour_competences
    ariane = chemin_collectif(classe, filtre, competence)
    retour = retour_competences(request, classe)
    if retour:
        chemin = urlsplit(retour).path
        if chemin == reverse("grille_classe", args=[classe.pk]):
            libelle_retour = "Grille de suivi"
        else:
            libelle_retour = "Compétences" if chemin == reverse("catalogue_competences", args=[classe.pk]) else ariane[-1][0]
        ariane[-1] = (libelle_retour, retour)
    return render(
        request,
        "suivi/saisie_competence.html",
        {"classe": classe, "competence": competence, "lignes": lignes, "filtre": filtre,
         "ariane": ariane,
         "adoption": adoption_courante(classe),
         "historique": classe_historique(classe),
         "nouvelle_saisie_possible": saisissable,
         "nombre_traces_communes": TraceCommune.objects.filter(
             classe=classe, competence=competence, supprime_le__isnull=True).count(),
         "correspondances": correspondances_classe(classe, competence.pk),
         "responsable": autorise(request.user, MODIFIER_ETAT, classe) and saisissable},
    )


def _contexte_grille_competence(request, pk, competence_pk=None, operation=VOIR_SUIVI,
                                *, impression=False):
    from .selection_editions import FiltresEdition, en_tetes, groupes_colonnes

    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, operation, ecole=ecole)
    competence = None
    if competence_pk is not None:
        competence = competence_classe(classe, get_object_or_404(
            Competence, pk=competence_pk, domaine__ecole=ecole))
        if competence is None:
            raise Http404

    filtre = filtre_competences(request)
    cle = f"grille:{ecole.pk}:{classe.pk}:{classe.annee_scolaire}"
    acces_direct = bool(competence or request.GET.get("filtres") or impression)
    if request.GET.get("reinitialiser") and not impression and not competence:
        request.session.pop(cle, None)
    donnees = request.GET if acces_direct else QueryDict(mutable=True)
    if not acces_direct:
        for nom, valeurs in request.session.get(cle, {}).items():
            donnees.setlist(nom, valeurs)
    # Les sélections mémorisées sont revalidées à chaque lecture.
    formulaire = FiltresEdition(classe, donnees, competence=competence)
    valide = formulaire.is_valid()
    if not valide and not acces_direct:
        for nom in formulaire.errors:
            donnees.pop(nom, None)
        formulaire = FiltresEdition(classe, donnees, competence=competence)
        valide = formulaire.is_valid()
        if not valide:
            formulaire = FiltresEdition(classe, {}, competence=competence)
            valide = formulaire.is_valid()
        request.session.pop(cle, None)
        messages.info(request, "Certains filtres mémorisés ne sont plus disponibles.")
    parametres = formulaire.parametres()
    if valide and request.GET.get("filtres") and not request.GET.get("origine") and not competence and not impression:
        request.session[cle] = dict(parametres.lists())
    eleves = formulaire.enfants(tous=True) if valide else []
    colonnes = formulaire.competences_retenues(eleves, force=competence) if valide else []
    etats = {(o.eleve_id, o.competence_id): projeter_etat_classe(o)
        for o in observations_classe(classe).filter(eleve_id__in=[e.pk for e in eleves],
                                                  competence_id__in=[c.competence.pk for c in colonnes])}
    compteurs = dict.fromkeys(("a_observer", "en_cours", "reussi", "non_retrouve"), 0)
    presentation = formulaire.cleaned_data.get("compacte")
    compacte = presentation == "oui" or (not presentation and len(colonnes) > 6)
    if not impression and not classe_historique(classe) and autorise(request.user, CONTRIBUER, classe, ecole=ecole):
        for eleve in eleves:
            scolarite = eleve.scolarite_courante()
            eleve.ouvrir_trace_grille = bool(scolarite and scolarite.classe_id == classe.pk)
    if not impression:
        classe_active = not classe_historique(classe)
        for eleve in eleves:
            courante = eleve.scolarite_courante()
            if (classe_active and not eleve.archive_le and courante and courante.classe_id == classe.pk
                    and autorise(request.user, VOIR_SUIVI, eleve)):
                eleve.url_ligne_grille = reverse("saisie_eleve", args=[eleve.pk])
            elif autorise(request.user, PREVISUALISER_CARNET, eleve):
                scolarites_visibles, _ = _scolarites_visibles(request.user, eleve)
                if scolarites_visibles.filter(annee_scolaire=classe.annee_scolaire).exists():
                    eleve.url_ligne_grille = reverse("carnet", args=[eleve.pk]) + "?annee=" + classe.annee_scolaire
    groupes = []
    if presentation == "lecture":
        blocs = ([colonne] for colonne in colonnes)
    else:
        blocs = groupes_colonnes(colonnes, 20 if compacte else 6) if impression else [colonnes]
    for colonnes_bloc in blocs:
        if not colonnes_bloc:
            continue
        lignes = []
        for eleve in eleves:
            cases = []
            for colonne in colonnes_bloc:
                c = colonne.competence
                observation = etats.get((eleve.pk, c.pk))
                if c.suivi_libre and eleve.pk not in c.eleves_suivis_ids:
                    etat = "hors_suivi"
                elif observation and observation.historique_inconnu:
                    etat = "non_retrouve"
                elif observation and observation.statut in (Observation.REUSSI, Observation.EN_COURS):
                    etat = observation.statut
                else:
                    etat = "a_observer"
                if etat in compteurs:
                    compteurs[etat] += 1
                cases.append((colonne, etat))
            lignes.append((eleve, cases))
        groupes.append({
            "colonnes": colonnes_bloc, "lignes": lignes,
            "rubriques": en_tetes(colonnes_bloc, "rubrique"),
            "sous_rubriques": en_tetes(colonnes_bloc, "sous_rubrique"),
        })
    args = [classe.pk, competence.pk] if competence else [classe.pk]
    url_pdf = reverse("grille_competence_pdf" if competence else "grille_classe_pdf", args=args)
    url_grille = reverse("grille_competence" if competence else "grille_classe", args=args)
    qualification = formulaire.cleaned_data.get("observations") or (
        "tout" if competence or formulaire.cleaned_data.get("rubriques")
        or formulaire.cleaned_data.get("competences") else "observes")
    edition = parametres.copy()
    edition["observations"] = qualification
    if competence:
        edition.setlist("competences", [str(competence.pk)])
        edition.pop("rubriques", None)
        edition.pop("niveaux", None)
        edition["observations"] = "tout"
    edition.setlist("eleves", [str(e.pk) for e in eleves])
    return {
        "ariane": chemin_competence(classe, competence, filtre) if competence else chemin_collectif(classe, filtre),
        "classe": classe, "competence": competence, "groupes": groupes, "compteurs": compteurs,
        "formulaire": formulaire, "eleves": formulaire.eleves,
        "selection_ids": {e.pk for e in eleves}, "compacte": compacte, "nb_eleves": len(eleves),
        "nb_competences": len(colonnes), "edite_le": timezone.localdate(), "filtre": filtre,
        "url_pdf": url_pdf + "?" + parametres.urlencode(), "url_grille": url_grille,
        "retour_grille": url_grille + "?filtres=1&" + parametres.urlencode(),
        "a_des_filtres": bool(parametres),
        "qualification_observations": qualification,
        "resume_rubriques": [label for valeur, label in formulaire.fields["rubriques"].choices
                            if valeur in formulaire.cleaned_data.get("rubriques", ())],
        "url_edition": reverse("preparer_edition", args=[classe.pk]) + "?" + edition.urlencode(),
        "peut_generer": autorise(request.user, GENERER_CARNET, classe, ecole=ecole),
    }


@acces_requis
@require_safe
def grille_competence(request, pk, competence_pk=None):
    return render(request, "suivi/grille_competence.html",
                  _contexte_grille_competence(request, pk, competence_pk))


@never_cache
@acces_requis
@require_safe
def grille_competence_pdf(request, pk, competence_pk=None):
    contexte = _contexte_grille_competence(request, pk, competence_pk, GENERER_CARNET, impression=True)
    if contexte["formulaire"].errors or not contexte["nb_competences"]:
        return render(request, "suivi/grille_competence.html", contexte, status=400)
    if getattr(settings, "MODE_PWA", False):
        return render(request, "suivi/grille_competence.html", {**contexte, "impression_pwa": True})
    html = render_to_string("suivi/grille_competence.html", {**contexte, "generation_pdf": True}, request=request)
    contenu = _generer_pdf(html, request.build_absolute_uri("/"), finders.find("suivi/carnet.css"))
    classe, competence = contexte["classe"], contexte["competence"]
    identifiant = competence.pk if competence else None
    journaliser(request.user, "pdf.grille_genere", classe,
                nouvelles={"competence_id": identifiant, "taille": len(contenu)})
    journaliser(request.user, "pdf.grille_telecharge", classe, nouvelles={"competence_id": identifiant})
    nom_classe = slugify(classe.nom) or "classe"
    suffixe = "-" + (slugify(competence.code) or "competence") if competence else ""
    return _reponse_pdf(contenu, f"grille-{nom_classe}{suffixe}.pdf")


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

    ouvrir_dates = bool(obs and obs.date_derniere_reussite and obs.statut != Observation.REUSSI)
    suivant = SUITE[obs.statut if obs else None]

    obs = modifier_etat(
        utilisateur=request.user,
        eleve=eleve,
        competence=competence,
        statut=suivant,
    )

    scolarite = eleve.scolarite_courante()
    if scolarite:
        competence = competence_classe(scolarite.classe, competence) or competence
    eleve.peut_saisir_dans_classe = True
    gabarit = (
        "suivi/partiels/case_eleve.html"
        if request.GET.get("vue") == "classe"
        else "suivi/partiels/case_competence.html"
    )
    return render(
        request,
        gabarit,
        {"eleve": eleve, "classe": scolarite.classe if scolarite else None,
         "competence": competence, "obs": obs, "filtre": filtre_competences(request), "responsable": True, "ouvrir_dates": ouvrir_dates,
         "adoption": adoption_courante(scolarite.classe) if scolarite else None},
    )


@acces_requis
@require_http_methods(["GET", "POST"])
def date_reussite(request, eleve_pk, competence_pk):
    from .forms_dates import DateReussiteForm
    eleve = charger_eleve_autorise(request.user, eleve_pk, MODIFIER_ETAT,
        ecole=ecole_courante(request), actifs_seulement=True)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=eleve.ecole)
    sc = eleve.scolarite_courante()
    if not sc or not competence_saisissable(sc.classe, competence, eleve=eleve):
        raise PermissionDenied
    obs = get_object_or_404(Observation, eleve=eleve, competence=competence)
    from .models import bornes_annee_scolaire
    debut, fin = bornes_annee_scolaire(sc.annee_scolaire)
    precedente = (obs.date_reussite_precedente or obs.date_derniere_reussite) if obs.statut == Observation.REUSSI else obs.date_derniere_reussite
    if precedente and not debut <= precedente <= fin:
        precedente = None
    form = DateReussiteForm(request.POST if request.method == "POST" else None,
        precedente=precedente, annee=sc.annee_scolaire)
    if request.method == "POST" and form.is_valid():
        try:
            modifier_etat(utilisateur=request.user, eleve=eleve, competence=competence,
                statut=Observation.REUSSI, date_observation=form.cleaned_data.get("date"),
                conserver_date=form.cleaned_data["choix"] == "precedente")
            filtre = filtre_competences(request)
            if request.GET.get("vue") == "classe":
                return redirect(lien("saisie_competence", sc.classe_id, competence.pk, filtre=filtre, ancre=f"e{eleve.pk}"))
            return redirect(lien("saisie_eleve", eleve.pk, filtre=filtre, ancre=f"c{competence.pk}"))
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "suivi/date_reussite.html", {"form": form, "eleve": eleve,
        "competence": competence, "precedente": precedente})


@acces_requis
def trace(request, eleve_pk, competence_pk):
    return _editer_trace(request, eleve_pk, competence_pk)


@acces_requis
def modifier_trace(request, eleve_pk, competence_pk, trace_pk):
    return _editer_trace(request, eleve_pk, competence_pk, trace_pk)


def _contexte_traces_communes(request, pk, competence_pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, VOIR_SUIVI, ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    competence = competence_classe(classe, competence) or competence
    return classe, competence


@acces_requis
def traces_communes(request, pk, competence_pk):
    classe, competence = _contexte_traces_communes(request, pk, competence_pk)
    filtre = filtre_competences(request)
    communes = TraceCommune.objects.filter(
        classe=classe, competence=competence, supprime_le__isnull=True
    ).prefetch_related(Prefetch("attributions", queryset=Trace.objects.filter(
        supprime_le__isnull=True
    ), to_attr="attributions_actives"))
    return render(request, "suivi/traces_communes.html", {
        "classe": classe, "competence": competence, "communes": communes,
        "ariane": chemin_competence(classe, competence, filtre), "filtre": filtre,
        "responsable": autorise(request.user, MODIFIER_ETAT, classe),
        "peut_ajouter": competence_saisissable(classe, competence),
    })


@acces_requis
def editer_trace_commune(request, pk, competence_pk, commune_pk=None):
    classe, competence = _contexte_traces_communes(request, pk, competence_pk)
    if not autorise(request.user, MODIFIER_ETAT, classe):
        raise Http404
    filtre = filtre_competences(request)
    retour_eleve = None
    retour_url = None
    retour_id = request.POST.get("retour_eleve") or request.GET.get("retour_eleve")
    if retour_id:
        try:
            retour_id = int(retour_id)
        except ValueError:
            raise Http404
        retour_eleve = get_object_or_404(
            Eleve, pk=retour_id, ecole=classe.ecole, scolarites__classe=classe,
        )
        if not autorise(request.user, VOIR_SUIVI, retour_eleve, ecole=classe.ecole):
            raise Http404
        retour_url = lien("trace", retour_eleve.pk, competence.pk, filtre=filtre,
                           **({"classe": classe.pk} if request.GET.get("origine") == "classe" else {}))
    commune = None
    if commune_pk is not None:
        commune = get_object_or_404(TraceCommune, pk=commune_pk, classe=classe,
                                    competence=competence, supprime_le__isnull=True)
        if not (autorise(request.user, MODIFIER_ETAT, classe) or commune.auteur_id == request.user.pk):
            raise Http404
    eleves = list(avec_scolarites_pour_lecture(classe.eleves))
    from .suivi_libre import est_libre, eleves_suivis
    if est_libre(competence, classe):
        ids_suivis = eleves_suivis(classe, competence)
        eleves = [e for e in eleves if e.pk in ids_suivis]
    selection_ids = set(commune.attributions.filter(supprime_le__isnull=True).values_list(
        "observation__eleve_id", flat=True
    )) if commune else set()
    versions = list(Trace.objects.filter(origine_commune=commune, supprime_le__isnull=True)
                    .select_related("observation__eleve")) if commune else []
    versions_par_eleve = {trace.observation.eleve_id: trace for trace in versions}
    for eleve in eleves:
        eleve.version_personnelle = versions_par_eleve.get(eleve.pk)
    depuis_competence = request.GET.get("origine") == "competence"
    ariane = chemin_competence(classe, competence, filtre)
    if retour_url:
        libelle_retour = f"Retour aux traces de {retour_eleve.nom_court}"
        ariane.append((f"Trace de {retour_eleve.nom_court}", retour_url))
    elif depuis_competence:
        libelle_retour, retour_url = "Retour à la compétence", ariane[-1][1]
    else:
        retour_url = lien("traces_communes", pk, competence_pk, filtre=filtre)
        libelle_retour = "Retour aux traces communes"
        ariane.append(("Traces communes", retour_url))
    erreur = None
    saisie_trace = None
    commentaire = commune.commentaire if commune else ""
    date_observation = commune.date_observation if commune else timezone.localdate()
    if request.method == "POST":
        commentaire = request.POST.get("commentaire", "").strip()
        date_observation = request.POST.get("date_observation") or ""
        try:
            selection_ids = {int(pk) for pk in request.POST.getlist("eleves")}
            date_observation = datetime.strptime(date_observation, "%Y-%m-%d").date()
            photo = commune.photo if commune else None
            if request.POST.get("retirer_photo"):
                photo = None
            if request.FILES.get("photo"):
                photo = preparer_image(request.FILES["photo"])
            ancien_nom = commune.photo.name if commune and commune.photo else ""
            with transaction.atomic():
                commune_enregistree = enregistrer_commune(utilisateur=request.user, classe=classe,
                                   competence=competence, ids=selection_ids,
                                   valeurs={"commentaire": commentaire,
                                            "date_observation": date_observation,
                                            "photo": photo}, commune=commune)
                nouveau_nom = commune_enregistree.photo.name if commune_enregistree.photo else ""
                if ancien_nom and ancien_nom != nouveau_nom:
                    _supprimer_media_apres_validation(ancien_nom)
            messages.success(request, "Trace commune enregistrée.")
            return redirect(retour_url)
        except (ValueError, ValidationError) as exc:
            erreur = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            saisie_trace = request.POST
    trace_media = commune.attributions.filter(supprime_le__isnull=True).first() if commune else None
    return render(request, "suivi/formulaire_trace_commune.html", {
        "classe": classe, "competence": competence, "commune": commune, "filtre": filtre,
        "ariane": ariane, "libelle_retour": libelle_retour, "saisie_trace": saisie_trace,
        "eleves": eleves, "selection_ids": selection_ids,
        "versions": versions, "versions_ids": {t.observation.eleve_id for t in versions},
        "commentaire": commentaire, "date_observation": date_observation,
        "trace_media": trace_media, "erreur": erreur,
        "formulations": formulations_effectives(competence, classe),
        "retour_eleve": retour_eleve, "retour_url": retour_url,
        "apercu_eleves": [{"id": e.pk, "prenom": e.prenom, "nom": e.nom_court} for e in eleves],
    })


@acces_requis
def personnaliser_trace_commune(request, eleve_pk, competence_pk, trace_pk):
    if request.method != "POST":
        raise Http404
    ecole = ecole_courante(request)
    trace_obj = get_object_or_404(Trace, pk=trace_pk, observation__eleve_id=eleve_pk,
                                  observation__competence_id=competence_pk,
                                  observation__eleve__ecole=ecole, commune__isnull=False,
                                  supprime_le__isnull=True)
    personnaliser(utilisateur=request.user, trace=trace_obj)
    messages.success(request, "Version personnelle créée. Vous pouvez maintenant la modifier.")
    return redirect(_lien_trace(request, eleve_pk, competence_pk, trace_pk))


@acces_requis
def retirer_trace_commune(request, pk, competence_pk, commune_pk):
    if request.method != "POST":
        raise Http404
    classe, competence = _contexte_traces_communes(request, pk, competence_pk)
    commune = get_object_or_404(TraceCommune, pk=commune_pk, classe=classe,
                                competence=competence, supprime_le__isnull=True)
    supprimer_commune(utilisateur=request.user, commune=commune)
    messages.success(request, "Trace commune retirée. Les versions personnelles sont conservées.")
    return redirect(lien("traces_communes", pk, competence_pk, filtre=filtre_competences(request)))


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


@never_cache
@acces_requis
@require_safe
def media_referentiel(request, eleve_pk, pk):
    ecole = ecole_courante(request)
    eleve = charger_eleve_autorise(request.user, eleve_pk, VOIR_SUIVI, ecole=ecole)
    ressource = get_object_or_404(RessourceReferentiel.objects.select_related("annuel"), pk=pk, annuel__ecole=ecole)
    scolarites, _ = _scolarites_visibles(request.user, eleve)
    from .models import AdoptionReferentiel
    adoptions = AdoptionReferentiel.objects.filter(classe_id__in=scolarites.values("classe_id"), clos=True)
    finale_autorisee = any(ressource.pk in a.etat_final.get("ressources", []) for a in adoptions)
    initiale_autorisee = any(
        sc.annee_scolaire == ressource.annuel.annee_scolaire
        and any(r.get("photo") == ressource.fichier.name and r.get("mode") == "remplacer"
                and r.get("classe_id") in (None, sc.classe_id)
                for r in ressource.annuel.etat_initial.get("reglages", []))
        for sc in scolarites)
    if not (finale_autorisee or initiale_autorisee):
        raise Http404
    return FileResponse(default_storage.open(ressource.fichier.name, "rb"),
                        content_type=mimetypes.guess_type(ressource.fichier.name)[0] or "application/octet-stream")


def _supprimer_media_apres_validation(nom):
    if not nom:
        return

    def supprimer():
        if (Trace.objects.filter(photo=nom).exists()
                or TraceCommune.objects.filter(photo=nom).exists()
                or ReglagePresentation.objects.filter(photo=nom).exists()
                or RessourceReferentiel.objects.filter(fichier=nom).exists()):
            return
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
    return redirect(_lien_trace(request, eleve_pk, competence_pk))


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
    return redirect(_lien_trace(request, eleve_pk, competence_pk))


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
    return redirect(_lien_trace(request, eleve_pk, competence_pk))


def _lien_trace(request, eleve_pk, competence_pk, trace_pk=None):
    classe = request.GET.get("classe", "")
    args = (eleve_pk, competence_pk)
    if trace_pk is not None:
        args += (trace_pk,)
    return lien("trace" if trace_pk is None else "modifier_trace", *args,
                filtre=filtre_competences(request), **({"classe": classe} if classe.isdecimal() else {}))


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
    competence_collective = competence_classe(scolarite_courante.classe, competence) if scolarite_courante else None
    competence = competence_collective or competence
    filtre = filtre_competences(request)
    suivi_complet = autorise(request.user, VOIR_SUIVI, eleve, ecole=ecole)
    classe = scolarite_courante.classe if scolarite_courante else None
    collectif = bool(
        classe and request.GET.get("classe") == str(classe.pk)
        and autorise(request.user, VOIR_SUIVI, classe, ecole=ecole)
        and competence_collective
    )
    precedent = suivant = None
    trace_query = lien("trace", eleve.pk, competence.pk, filtre=filtre).partition("?")[2]
    if collectif:
        ariane = chemin_competence(classe, competence, filtre, ancre=f"e{eleve.pk}")
        retour = ariane[-1][1]
        trace_query = lien("trace", eleve.pk, competence.pk, filtre=filtre, classe=classe.pk).partition("?")[2]
        from .navigation import retour_competences
        depuis_grille = retour_competences(request, classe)
        if depuis_grille and urlsplit(depuis_grille).path == reverse("grille_classe", args=[classe.pk]):
            ariane.insert(-1, ("Grille de suivi", depuis_grille))
            retour = depuis_grille
            trace_query += "&" + urlencode({"retour": depuis_grille})
        if (not classe_historique(classe) and competence_saisissable(classe, competence)
                and autorise(request.user, CONTRIBUER, classe, ecole=ecole)):
            # Même ordre que la liste collective, avec la scolarité active et les droits de contribution.
            voisins = [
                enfant for enfant in avec_scolarites_pour_lecture(classe.eleves)
                if enfant.scolarite_courante() and enfant.scolarite_courante().classe_id == classe.pk
                and (not competence.suivi_libre or enfant.pk in competence.eleves_suivis_ids)
            ]
            for position, enfant in enumerate(voisins):
                if enfant.pk == eleve.pk:
                    precedent = voisins[position - 1] if position else None
                    suivant = voisins[position + 1] if position + 1 < len(voisins) else None
                    break
    else:
        ariane = chemin_classe(classe) if classe and autorise(request.user, VOIR_CLASSE, classe, ecole=ecole) else []
        retour = lien("saisie_eleve" if suivi_complet else "contribuer_eleve", eleve.pk,
                      filtre=filtre, ancre=f"c{competence.pk}" if suivi_complet else "")
        ariane.append((eleve.nom_court, retour))
    saisie = None
    if obs is None and trace_pk is None and scolarite_courante:
        from .suivi_libre import verifier_portee
        verifier_portee(scolarite_courante.classe, competence, eleve=eleve)
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
        if trace_obj.commune_id:
            raise Http404
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
        try:
            if request.FILES.get("photo"):
                photo = preparer_image(request.FILES["photo"])
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
            if collectif:
                if suivant and request.POST.get("navigation") == "suivant":
                    return redirect(lien("trace", suivant.pk, competence.pk, filtre=filtre, classe=classe.pk))
                return redirect(retour)
            return redirect(lien("trace", eleve.pk, competence.pk, filtre=filtre))
        except (ValueError, ValidationError) as exc:
            saisie = request.POST
            messages.error(
                request,
                " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc),
            )

    traces = (
        obs.traces.filter(
            scolarite=scolarite_courante,
            supprime_le__isnull=True,
        ).select_related("scolarite__classe__ecole", "commune", "origine_commune")
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
        trace_conservee.peut_telecharger_original = bool(trace_conservee.photo) and autorise(
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
        for retiree in traces_supprimees:
            autre_version = obs.traces.filter(supprime_le__isnull=True).filter(
                Q(commune_id=retiree.origine_commune_id)
                if retiree.origine_commune_id else
                Q(origine_commune_id=retiree.commune_id)
                if retiree.commune_id else Q(pk=-1)
            ).exists()
            retiree.peut_restaurer = not autre_version and not (
                retiree.commune_id and retiree.commune.supprime_le
            )
    return render(
        request,
        "suivi/trace.html",
        {
            "eleve": eleve,
            "competence": competence,
            "obs": obs,
            "ariane": ariane,
            "retour_trace": retour,
            "page_trace": f"Trace de {eleve.nom_court}",
            "contexte_trace": "?" + trace_query if trace_query else "",
            "collectif": collectif,
            "filtre": filtre,
            "precedent": precedent,
            "suivant": suivant,
            "saisie_trace": saisie,
            "erreur_trace": saisie is not None,
            "trace_obj": trace_obj,
            "peut_ajouter": bool(scolarite_courante and competence_saisissable(scolarite_courante.classe, competence, eleve=eleve)),
            "traces": traces,
            "traces_supprimees": traces_supprimees,
            "responsable": responsable,
            "suivi_complet": suivi_complet,
            "formulations": [
                personnaliser_texte(texte, eleve.prenom)
                for texte in formulations_effectives(competence, scolarite_courante.classe if scolarite_courante else None)
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
    from .selection_editions import options_carnet

    presentation = options_carnet(options, parametres, cases_postees=options.get("options_appliquees") == "1")
    mode = presentation["contenu"]
    colonnes = presentation["colonnes"]
    regroupement = presentation["regroupement"]
    afficher_attendus = presentation["attendus"] == "1"
    afficher_sous_domaines = presentation["sous_domaines"] == "1"
    inclure_bilans = presentation["bilans"] == "1"

    scolarites_visibles, courante = _scolarites_visibles(request.user, eleve)
    annee_selectionnee = options.get("annee", "")
    scolarite = courante
    if annee_selectionnee:
        scolarite = scolarites_visibles.filter(annee_scolaire=annee_selectionnee).select_related("classe").first()
        if scolarite is None:
            raise Http404
    classe_presentation = scolarite.classe if scolarite else None
    adoption = adoption_courante(classe_presentation)
    historique = bool(annee_selectionnee and (courante is None or scolarite.pk != courante.pk or (adoption and adoption.clos)))
    etats_inconnus = False
    if historique:
        etats, etats_inconnus = observations_annee(eleve, scolarite)
    else:
        etats = {o.competence_id: o for o in _observations_visibles(request.user, eleve).select_related("competence")}
        for observation in etats.values():
            observation.traces_carnet = [
                trace for trace in observation.traces.all()
                if trace.visible_carnet and trace.supprime_le is None
                and (not annee_selectionnee or trace.scolarite_id == scolarite.pk)
            ]
    if annee_selectionnee:
        scolarites_bilans = scolarites_visibles.filter(pk=scolarite.pk)
    else:
        scolarites_bilans = scolarites_visibles
    if periode := options.get("periode_traces"):
        debut, fin = periode
        for observation in etats.values():
            observation.traces_carnet = [trace for trace in observation.traces_carnet
                if debut <= trace.date_observation <= fin]
    for observation in etats.values():
        observation.a_reussite_datee = any(t.reussite for t in observation.traces_carnet)
    domaines = []
    # Une lecture commune pour tous les domaines et acquisitions. Les titres
    # annuels conservent les niveaux réellement inscrits, y compris hors des
    # scolarités dont les traces sont visibles dans ce carnet.
    scolarites_par_annee = ({s.annee_scolaire: s for s in eleve.scolarites.all()}
                           if regroupement == "annuel" else {})
    bilans_regroupement = (list(Bilan.objects.filter(
        scolarite__eleve=eleve, scolarite__in=scolarites_bilans,
        supprime_le__isnull=True).select_related("scolarite").order_by("date_bilan"))
        if regroupement == "bilan" else [])
    selection_competences = options.get("selection_competences")
    for d in _arbre(ecole, classe=classe_presentation, inclure_ids=etats, eleve=eleve):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles
                  if selection_competences is None or c.pk in selection_competences]
        if mode == "reussites":
            lignes = [
                (c, o) for c, o in lignes if o and (o.statut == Observation.REUSSI or o.a_reussite_datee)
            ]
        elif mode == "observes":
            lignes = [
                (c, o)
                for c, o in lignes
                if o and (o.statut in (Observation.REUSSI, Observation.EN_COURS) or o.a_reussite_datee or (historique and o.traces_carnet))
            ]
        if lignes:
            domaines.append(
                (
                    d,
                    _regrouper_lignes(
                        eleve, lignes, regroupement, scolarites_bilans,
                        scolarites_par_annee=scolarites_par_annee, bilans=bilans_regroupement,
                    ),
                )
            )

    reglages = reglages_du_perimetre(ecole, classe_presentation)
    couverture = illustration_effective(ecole, classe=classe_presentation, reglages=reglages, historique=historique)
    avec_photos = affichage_avec_photos(ecole, classe_presentation, historique=historique)
    credits = set()
    a_illustrations = False
    if couverture.photo and (credit := credit_illustration(couverture)):
        credits.add(credit)
    for _domaine, groupes in domaines:
        for _titre, lignes in groupes:
            for competence, _observation in lignes:
                competence.illustration = illustration_effective(ecole, competence, classe_presentation, reglages, historique=historique)
                image = competence.illustration
                competence.afficher_illustration = avec_photos or not any(
                    trace.photo for trace in getattr(_observation, "traces_carnet", []))
                competence.url_icone = ((reverse("media_referentiel", args=[eleve.pk, image.ressource_id]) if image.ressource_id else reverse("media_presentation", args=[image.reglage_id])) if image.photo
                                        else static(image.statique) if image.statique else "")
                if competence.afficher_illustration and competence.url_icone:
                    a_illustrations = True
                    if credit := credit_illustration(image):
                        credits.add(credit)
    bilans = (
        Bilan.objects.filter(
            scolarite__eleve=eleve,
            scolarite__in=scolarites_bilans,
            visible_carnet=True,
            supprime_le__isnull=True,
        ).select_related("scolarite")
        if inclure_bilans
        else Bilan.objects.none()
    )

    return {
        "presentation": presentation,
        "annee_selectionnee": annee_selectionnee,
        "scolarites_proposees": scolarites_visibles.select_related("classe"),
        "etats_historiques_inconnus": etats_inconnus,
        "presentation_initiale_reprise": bool(annee_selectionnee and adoption and adoption.reprise and not adoption.clos),
        "eleve": eleve,
        "domaines": domaines,
        "mode": mode,
        "colonnes": colonnes,
        "regroupement": regroupement,
        "scolarite": scolarite,
        "bilans": bilans,
        "parametres_carnet": parametres,
        "illustration_couverture": couverture,
        "credits_illustrations": [CREDITS_IMAGES[cle] for cle in sorted(credits)],
        "a_illustrations": a_illustrations,
        "url_photo_couverture": (reverse("media_referentiel", args=[eleve.pk, couverture.ressource_id]) if couverture.ressource_id else reverse("media_presentation", args=[couverture.reglage_id])) if couverture.photo else "",
        "afficher_attendus": afficher_attendus,
        "afficher_sous_domaines": afficher_sous_domaines,
        "inclure_bilans": inclure_bilans,
        "edite_le": timezone.localdate(),
        "classe_edition": classe_presentation if classe_presentation and autorise(
            request.user, GENERER_CARNET, classe_presentation, ecole=ecole) else None,
        "peut_generer": autorise(
            request.user, GENERER_CARNET, eleve, ecole=ecole
        ),
    }


def _regrouper_lignes(eleve, lignes, regroupement, scolarites=None, *,
                     scolarites_par_annee=None, bilans=None):
    if regroupement == "aucun":
        return [(None, lignes)]

    if regroupement == "annuel" and scolarites_par_annee is None:
        scolarites_par_annee = {s.annee_scolaire: s for s in eleve.scolarites.all()}
    if regroupement == "bilan" and bilans is None:
        filtre_bilans = Bilan.objects.filter(
            scolarite__eleve=eleve, supprime_le__isnull=True)
        if scolarites is not None:
            filtre_bilans = filtre_bilans.filter(scolarite__in=scolarites)
        bilans = list(filtre_bilans.select_related("scolarite").order_by("date_bilan"))
    groupes = OrderedDict()
    for competence, observation in lignes:
        if observation is None:
            titre = "À découvrir"
        elif getattr(observation, "historique_inconnu", False) and observation.date_observation is None:
            titre = "Année scolaire " + observation.annee_historique + " — état non retrouvé"
        elif regroupement == "mensuel":
            titre = date_format(observation.date_observation, "F Y").capitalize()
        elif regroupement == "annuel":
            annee = annee_scolaire_pour(observation.date_observation)
            scolarite = scolarites_par_annee.get(annee)
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
    from pas_communs.pdf import url_media
    return url_media(nom, schema=SCHEMA_MEDIA_PDF)


def _recuperateur_pdf(noms_media):
    from pas_communs.pdf import recuperateur_medias
    # Conserver l'API, le stockage et la politique historique des autres URL.
    return recuperateur_medias(noms_media, schema=SCHEMA_MEDIA_PDF,
                              ouvrir=default_storage.open)


def _generer_pdf(html, base_url, feuille_style, noms_media=()):
    from pas_communs.pdf import rendre_html
    return rendre_html(html, base_url=base_url, feuille_style=feuille_style,
                       recuperer=_recuperateur_pdf(noms_media))


@acces_requis
def carnet(request, pk):
    return render(
        request,
        "suivi/carnet.html",
        {**_contexte_carnet(request, pk), "retour_grille": _retour_grille_eleve(request)},
    )


@never_cache
@acces_requis
@require_safe
def carnet_pdf(request, pk):
    try:
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
    except Exception:
        if settings.MODE_LOCAL:
            # DEBUG est désactivé dans l'application autonome. Le lanceur
            # conserve stderr dans dernier-demarrage.log ; écrire la trace
            # ici évite de perdre la cause d'une réponse 500 lors du PDF.
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
        raise


def _medias_pdf_carnet(contexte):
    noms_media = []
    couverture = contexte["illustration_couverture"]
    if couverture.photo:
        contexte["url_photo_couverture_pdf"] = _url_media_pdf(couverture.photo)
        noms_media.append(couverture.photo)
    for _domaine, groupes in contexte["domaines"]:
        for _titre, lignes in groupes:
            for _competence, observation in lignes:
                image = _competence.illustration
                if not _competence.afficher_illustration:
                    pass
                elif image.photo:
                    _competence.url_icone_pdf = _url_media_pdf(image.photo)
                    noms_media.append(image.photo)
                elif image.statique:
                    fichier = finders.find(image.statique)
                    if not fichier:
                        raise RuntimeError("Une icône fournie est introuvable.")
                    _competence.url_icone_pdf = Path(fichier).resolve().as_uri()
                if observation:
                    for trace_obj in observation.traces_carnet:
                        if trace_obj.photo:
                            trace_obj.url_photo_pdf = _url_media_pdf(trace_obj.photo.name)
                            noms_media.append(trace_obj.photo.name)
    return noms_media


def _reponse_pdf(contenu, nom):
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


def _contenu_pdf_carnet(request, pk, options=None, operation=GENERER_CARNET):
    contexte = _contexte_carnet(request, pk, options, operation)
    noms_media = _medias_pdf_carnet(contexte)
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


def _archive_carnets(request, classe, eleves, options):
    archive = BytesIO()
    noms_utilises = set()
    with ZipFile(archive, "w", ZIP_DEFLATED) as fichiers:
        for eleve in eleves:
            contenu, nom = _contenu_pdf_carnet(request, eleve.pk, options)
            base, extension = nom.rsplit(".", 1)
            candidat = nom
            numero = 2
            while candidat in noms_utilises:
                candidat = f"{base}-{numero}.{extension}"
                numero += 1
            noms_utilises.add(candidat)
            fichiers.writestr(candidat, contenu)
    reponse = HttpResponse(archive.getvalue(), content_type="application/zip")
    nom_classe = slugify(classe.nom) or "classe"
    reponse["Content-Disposition"] = f'attachment; filename="carnets-{nom_classe}.zip"'
    nouvelles = {"nombre_eleves": len(eleves), "taille": len(archive.getvalue())}
    journaliser(request.user, "zip.classe_genere", classe, nouvelles=nouvelles)
    journaliser(request.user, "zip.classe_telecharge", classe, nouvelles=nouvelles)
    return reponse


@never_cache
@acces_requis
@require_http_methods(["GET", "POST"])
def preparer_edition(request, pk):
    from .selection_editions import FiltresEdition, options_carnet

    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, GENERER_CARNET, ecole=ecole)
    donnees = request.POST if request.method == "POST" else request.GET
    filtres = donnees.copy()
    formulaire = FiltresEdition(classe, filtres)
    eleves = formulaire.eleves
    ids = {str(e.pk) for e in eleves}
    filtres.setlist("eleves", [v for v in donnees.getlist("eleves") if v in ids])
    valide = formulaire.is_valid()
    selection = formulaire.enfants() if valide else []
    mode_pwa = getattr(settings, "MODE_PWA", False)
    format_edition = donnees.get("format", "pdf" if mode_pwa else "zip")
    cartes = format_edition == "cartes"
    parametres, _ = ParametresCarnet.objects.get_or_create(ecole=ecole)
    cle_options = f"edition:{ecole.pk}:{classe.pk}:{classe.annee_scolaire}:{format_edition}"
    explicite = request.method == "POST" or any(cle in donnees for cle in ("contenu", "colonnes", "regroupement"))
    presentation = options_carnet(donnees if explicite else request.session.get(cle_options, {}),
                                  parametres, cases_postees=request.method == "POST")
    parcours_complet = donnees.get("parcours") == "complet" and format_edition in {"pdf", "zip", "sequence"}
    champs_cartes = ("unite", "ordre_cartes", "avec_photo", "avec_commentaire",
                     "espace_eleve", "grandes_cartes", "planches_compactes")
    if request.method == "POST" or "reglages_cartes" in donnees:
        choix_cartes = {cle: donnees[cle] for cle in champs_cartes if cle in donnees}
    else:
        choix_cartes = request.session.get(cle_options + ":cartes", {"avec_photo": "on"})
    if request.method == "POST" and valide and selection:
        if format_edition == "grille":
            criteres = formulaire.parametres()
            criteres["filtres"] = "1"
            criteres["origine"] = "edition"
            return redirect(reverse("grille_classe", args=[classe.pk]) + "?" + criteres.urlencode())
        if format_edition not in {"pdf", "sequence", "cartes", "zip"}:
            raise Http404
        request.session[cle_options] = presentation
        options = {**presentation, "annee": "" if parcours_complet else classe.annee_scolaire}
        if formulaire.cleaned_data.get("observations") in {"periode", "reussites"}:
            options["periode_traces"] = (formulaire.cleaned_data["debut"], formulaire.cleaned_data["fin"])
        if cartes:
            request.session[cle_options + ":cartes"] = choix_cartes
            options["contenu"] = "tout"
            options["regroupement"] = "aucun"
            options["bilans"] = "0"
        champs_competences = ("competences", "rubriques", "niveaux", "observations")
        if cartes or any(formulaire.cleaned_data.get(c) for c in champs_competences):
            colonnes = formulaire.competences_retenues(selection)
            options["selection_competences"] = {c.competence.pk for c in colonnes}
        if format_edition == "zip" and not mode_pwa and donnees.get("action") != "apercu":
            return _archive_carnets(request, classe, selection, options)
        if format_edition == "sequence":
            cible = donnees.get("carnet")
            if cible is None:
                return render(request, "suivi/edition_sequence.html", {
                    "classe": classe, "eleves": selection,
                    "champs": [(cle, valeur) for cle, valeurs in donnees.lists()
                               if cle not in {"csrfmiddlewaretoken", "carnet"} for valeur in valeurs],
                })
            selection = [e for e in selection if str(e.pk) == cible]
            if not selection:
                raise Http404
            if not mode_pwa:
                contenu, nom = _contenu_pdf_carnet(request, selection[0].pk, options)
                return _reponse_pdf(contenu, nom)
        contextes = [_contexte_carnet(request, e.pk, options, GENERER_CARNET) for e in selection]
        medias = []
        generation_pdf = not mode_pwa and donnees.get("action") != "apercu"
        if generation_pdf:
            for contexte in contextes:
                medias.extend(_medias_pdf_carnet(contexte))
        retour = QueryDict(mutable=True)
        for cle in (*formulaire.fields, "format", "parcours", "mise_en_page_ouverte", "unite", "avec_photo",
                    "avec_commentaire", "espace_eleve", "grandes_cartes", "planches_compactes",
                    "ordre_cartes"):
            if cle in donnees:
                retour.setlist(cle, donnees.getlist(cle))
        retour.update(presentation)
        if cartes:
            retour["reglages_cartes"] = "1"
        contexte = {
            "carnets": contextes, "classe": classe, "generation_pdf": generation_pdf,
            "retour_edition": reverse("preparer_edition", args=[classe.pk]) + "?" + retour.urlencode(),
        }
        gabarit = "suivi/edition_imprimable.html"
        nom = f"carnets-{slugify(classe.nom) or 'classe'}.pdf"
        if cartes:
            from .selection_editions import planches_cartes
            contexte["planches"] = planches_cartes(contextes, donnees, formulaire.cleaned_data)
            contexte["nombre_cartes"] = sum(map(len, contexte["planches"]))
            contexte["textes_longs"] = any(len(c["trace"].commentaire) > 180
                for planche in contexte["planches"] for c in planche if c["trace"])
            contexte["credits_cartes"] = {c["url"]: c for carnet in contextes
                for c in carnet["credits_illustrations"]}.values()
            contexte["grandes_cartes"] = "grandes_cartes" in donnees
            contexte["avec_commentaire"] = "avec_commentaire" in donnees
            contexte["avec_photo"] = "avec_photo" in donnees
            contexte["espace_eleve"] = "espace_eleve" in donnees
            gabarit = "suivi/cartes_imprimables.html"
            nom = f"cartes-{slugify(classe.nom) or 'classe'}.pdf"
        else:
            # Le fragment commun échappe le contenu de chaque carnet.
            contexte["carnets"] = [mark_safe(render_to_string(
                "suivi/partiels/carnet_contenu.html",
                {**carnet, "generation_pdf": generation_pdf, "apercu_groupe": not generation_pdf}, request=request,
            )) for carnet in contextes]
        if not generation_pdf:
            return render(request, gabarit, contexte)
        html = render_to_string(gabarit, contexte, request=request)
        contenu = _generer_pdf(html, request.build_absolute_uri("/"),
                               finders.find("suivi/carnet.css"), medias)
        journaliser(request.user, "pdf.edition_classe_generee", classe,
                    nouvelles={"format": format_edition, "nombre_eleves": len(selection), "taille": len(contenu)})
        return _reponse_pdf(contenu, nom)

    if request.method == "POST" and valide:
        messages.error(request, "Sélectionnez au moins un élève.")
    return render(request, "suivi/preparer_edition.html", {
        "classe": classe, "eleves": eleves, "formulaire": formulaire,
        "selection_ids": {e.pk for e in eleves if str(e.pk) in filtres.getlist("eleves")},
        "ouvrir_filtres": not selection,
        "mise_en_page_ouverte": donnees.get("mise_en_page_ouverte", ""),
        "presentation": presentation, "format_edition": format_edition,
        "parcours_complet": parcours_complet,
        "choix_cartes": choix_cartes,
    })


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
    from .services.garde_fous_referentiels import demarrage_ecole
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
            "demarrage_ecole": est_direction(request.user, ecole) and demarrage_ecole(ecole),
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
            if action in {"accorder_gestion", "retirer_gestion"}:
                formulaire = DroitsGestionForm(request.POST)
                if not formulaire.is_valid():
                    raise ValidationError([message for erreurs in formulaire.errors.values() for message in erreurs])
                # Réutiliser la confirmation sensible : même authentification
                # et protection contre les essais que les changements de base.
                verifier_confirmation(request)
                if action == "accorder_gestion":
                    membre = get_object_or_404(AppartenanceEcole,
                        pk=request.POST.get("appartenance"), ecole=ecole)
                    attribuer_direction(utilisateur=request.user, appartenance=membre,
                        date_fin=formulaire.cleaned_data["date_fin"], motif=formulaire.cleaned_data["motif"])
                    messages.success(request, "Droits de gestion accordés.")
                else:
                    responsabilite = get_object_or_404(ResponsabiliteEcole,
                        pk=request.POST.get("responsabilite"), appartenance__ecole=ecole)
                    terminer_direction(utilisateur=request.user, responsabilite=responsabilite,
                        motif=formulaire.cleaned_data["motif"])
                    messages.success(request, "Droits de gestion retirés. Les fonctions de classe sont conservées.")
                # Recalcul immédiat pour l'acteur s'il a retiré ses propres droits.
                request.session.pop("double_facteur_exigence", None)
                if not est_direction(request.user, ecole):
                    if not autorise(request.user, ACCEDER_APPLICATION, ecole=ecole):
                        logout(request)
                        return redirect("connexion")
                    return redirect("accueil")
            elif action == "inviter":
                invitation, jeton = inviter(
                    utilisateur=request.user,
                    ecole=ecole,
                    email=request.POST.get("email", ""),
                )
                classe_preattribuee_id = request.POST.get("classe_preattribuee")
                type_preattribuee = request.POST.get("type_preattribuee")
                preattribution = None
                if classe_preattribuee_id and type_preattribuee:
                    classe_preattribuee = get_object_or_404(
                        Classe, pk=classe_preattribuee_id, ecole=ecole
                    )
                    preattribution = attribuer_affectation(
                        utilisateur=request.user,
                        classe=classe_preattribuee,
                        type=type_preattribuee,
                        invitation=invitation,
                    )
                lien = request.build_absolute_uri(
                    reverse(
                        "accepter_invitation",
                        args=[invitation.selecteur, jeton],
                    )
                )
                request.session["lien_invitation_creee"] = lien
                suffixe_preattribution = (
                    f" et pré-attribuée comme {preattribution.get_type_display().lower()} "
                    f"de {preattribution.classe.libelle_avec_annee}"
                    if preattribution
                    else ""
                )
                if not settings.EMAIL_DISPONIBLE:
                    messages.warning(
                        request,
                        f"Invitation créée{suffixe_preattribution}. L’envoi de "
                        "courriel est désactivé : copiez le lien affiché "
                        "ci-dessous et transmettez-le vous-même.",
                    )
                elif envoyer_email_invitation(
                    utilisateur=request.user, invitation=invitation, lien=lien
                ):
                    messages.success(
                        request,
                        f"Invitation envoyée par e-mail à {invitation.email}"
                        f"{suffixe_preattribution}. Le lien reste aussi "
                        "affiché ci-dessous en secours, au cas où l’e-mail "
                        "n’arriverait pas.",
                    )
                else:
                    messages.warning(
                        request,
                        f"Invitation créée{suffixe_preattribution}, mais "
                        "l’envoi de l’e-mail a échoué. Copiez le lien "
                        "affiché ci-dessous et transmettez-le vous-même.",
                    )
            elif action == "lien_reinitialisation":
                membre = get_object_or_404(
                    AppartenanceEcole, pk=request.POST.get("appartenance"), ecole=ecole)
                request.session["lien_reinitialisation_creee"] = {
                    "lien": acces_local.lien_reinitialisation(
                        acteur=request.user, cible=membre.utilisateur, ecole=ecole,
                        requete=request),
                    "nom": membre.utilisateur.get_full_name() or membre.utilisateur.username}
            elif action == "reinitialiser_double_facteur":
                membre = get_object_or_404(
                    AppartenanceEcole, pk=request.POST.get("appartenance"), ecole=ecole)
                reinitialiser_par_la_direction(
                    acteur=request.user, cible=membre.utilisateur, ecole=ecole)
                messages.success(
                    request,
                    "Le second facteur de cette personne a été réinitialisé et ses "
                    "sessions ouvertes ont été fermées. Si votre politique l'exige "
                    "encore, elle devra le configurer de nouveau dès sa prochaine connexion.",
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
    if settings.DOUBLE_FACTEUR_DISPONIBLE:
        inscrits = set(DoubleFacteurCompte.objects.filter(
            utilisateur__in=[a.utilisateur_id for a in appartenances],
            confirme_le__isnull=False).values_list("utilisateur_id", flat=True))
        for appartenance in appartenances:
            appartenance.double_facteur_reinitialisable = (
                appartenance.utilisateur_id in inscrits
                and appartenance.est_active(aujourd_hui)
                and refus_reinitialisation(request.user, appartenance.utilisateur, ecole) is None
            )
    directions_gestion = []
    for appartenance in appartenances:
        appartenance.directions_actives = [r for r in appartenance.responsabilites.all()
            if r.type == ResponsabiliteEcole.DIRECTION and r.est_active(aujourd_hui)]
        directions_gestion.extend(appartenance.directions_actives)
    membres_gestion = [a for a in appartenances
        if a.est_active(aujourd_hui) and not a.directions_actives]
    avertissement_continuite = ""
    from .continuite_direction import verifier_continuite_direction
    try:
        verifier_continuite_direction(ecole.pk)
    except ValidationError as erreur:
        avertissement_continuite = " ".join(erreur.messages)
    membres_affectables = [
        appartenance
        for appartenance in appartenances
        if appartenance.est_active(aujourd_hui)
    ]
    # Les affectations ont été préchargées ci-dessus. Le test d'occupation
    # reprend exactement les dates et l'état du filtre de remplacement,
    # sans remplacer les contrôles de fin d'affectation ou de gouvernance.
    classes_occupees = {
        membre.pk: {a.classe_id for a in membre.affectations_classes.all()
                    if a.etat == AffectationClasse.ACTIVE
                    and a.date_debut <= aujourd_hui
                    and (a.date_fin is None or a.date_fin >= aujourd_hui)}
        for membre in membres_affectables
    }
    for appartenance in appartenances:
        for affectation in appartenance.affectations_classes.all():
            affectation.est_active_aujourdhui = affectation.est_active(aujourd_hui)
            affectation.gerable_aujourdhui = affectation.est_active_aujourdhui
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
                    and affectation.classe_id not in classes_occupees[candidat.pk]
                ]
    preattributions = list(
        AffectationClasse.objects.filter(
            invitation__ecole=ecole, appartenance__isnull=True
        ).select_related("invitation", "classe")
    )
    for affectation in preattributions:
        # Une pré-attribution n'accorde jamais d'accès réel (voir
        # AffectationClasse.est_active) : seule sa présence dans le
        # référentiel est « gérable », pour permettre à la direction de
        # l'annuler avant même que le compte n'existe.
        affectation.est_active_aujourdhui = False
        affectation.gerable_aujourdhui = affectation.preattribution_en_cours
        if affectation.gerable_aujourdhui:
            affectation.peut_terminer_directement = peut_terminer_affectation(
                request.user, affectation, date=aujourd_hui
            )
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
    for affectation in preattributions:
        preparer_affectation(affectation)
        # Annulée, révoquée ou expirée : elle ne figure plus parmi les
        # fonctions présentes, seulement dans l'historique.
        affectation.est_presente_ou_future = (
            affectation.est_presente_ou_future and affectation.preattribution_en_cours
        )
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
            "directions_gestion": directions_gestion,
            "membres_gestion": membres_gestion,
            "avertissement_continuite": avertissement_continuite,
            "appartenances": personnes_visibles,
            "membres_affectables": membres_affectables,
            "invitations": invitations,
            "lien_reinitialisation_creee": request.session.pop("lien_reinitialisation_creee", None),
            "lien_reinitialisation_possible": acces_local.disponible(),
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
    from django.core import signing
    from .forms import CreationClasseForm
    from .services.creation_classe import creer_classe_avec_base

    ecole = ecole_courante(request)
    initial = {"annee_scolaire": request.GET.get("annee_scolaire", annee_scolaire_pour(timezone.localdate())),
               "nom": request.GET.get("nom", "")}
    formulaire = CreationClasseForm(request.POST or None, ecole=ecole, initial=initial)
    if request.method == "POST" and formulaire.is_valid():
        try:
            donnees = formulaire.cleaned_data
            try:
                choix_lus = signing.loads(donnees["jeton_choix"], salt="creation-classe", max_age=1800)
            except signing.BadSignature as cause:
                raise ValidationError("Les propositions ont expiré. Vérifiez le référentiel affiché avant de créer la classe.") from cause
            if (choix_lus["ecole"] != ecole.pk or choix_lus["auteur"] != request.user.pk or
                    choix_lus["annee"] != donnees["annee_scolaire"]):
                raise ValidationError("Vérifiez les propositions pour l’année choisie avant de créer la classe.")
            classe = creer_classe_avec_base(utilisateur=request.user, ecole=ecole,
                nom=donnees["nom"], annee=donnees["annee_scolaire"], base=donnees["base"],
                revisions_attendues=choix_lus["revisions"],
                selection_manuelle=donnees.get("selection_manuelle", False))
            return redirect("importer_eleves", pk=classe.pk)
        except ValidationError as cause:
            formulaire.add_error(None, " ".join(cause.messages))
    choix = formulaire.choix
    jeton = signing.dumps({"ecole": ecole.pk, "auteur": request.user.pk,
        "annee": formulaire.annee, "revisions": choix.revisions if choix else None}, salt="creation-classe")
    # Une page refusée reçoit les propositions relues, jamais un ancien jeton.
    if formulaire.is_bound:
        formulaire.data = formulaire.data.copy()
        formulaire.data["jeton_choix"] = jeton
    else:
        formulaire.initial["jeton_choix"] = jeton
    return render(request, "suivi/creer_classe.html", {"formulaire": formulaire, "choix": choix})


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
    retour_pk = retour_pk if retour_pk and retour_pk.isdecimal() else None
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

    params = {}
    if retour_classe:
        params["retour"] = retour_classe.pk
        ariane = chemin_classe(retour_classe) + [
            ("Gérer les élèves", lien("importer_eleves", retour_classe.pk, ancre=f"eleve-{eleve.pk}")),
        ]
    else:
        ariane = [("Gérer l’école", lien("gestion"))] if direction else []
        if direction and request.GET.get("origine") == "annuaire":
            filtres = {}
            annee = request.GET.get("annee", "")
            if annee in _annees_disponibles(ecole):
                filtres["annee"] = annee
            for cle, valeurs in (("niveau", {"PS", "MS", "GS", "tous"}),
                                 ("etat", {"actifs", "archives", "tous"})):
                valeur = request.GET.get(cle)
                if valeur in valeurs:
                    filtres[cle] = valeur
            params = {"origine": "annuaire", **filtres}
            ariane.append(("Annuaire des élèves", lien("annuaire_eleves", **filtres)))

    def _retour_url():
        return lien("parcours_eleve", eleve.pk, **params)

    scolarite_a_corriger = eleve.scolarites.filter(classe=classe).first() if classe else None
    if scolarite_a_corriger and (eleve.archive_le or classe_historique(classe)
                                or not autorise(request.user, GERER_ELEVES_CLASSE, classe)):
        scolarite_a_corriger = None
    if request.method == "POST" and request.POST.get("action") == "niveau":
        if scolarite_a_corriger is None or request.POST.get("scolarite") != str(scolarite_a_corriger.pk):
            raise Http404
        niveau = request.POST.get("niveau")
        if niveau not in NIVEAUX_VALIDES:
            messages.error(request, "Choisissez un niveau valide.")
        else:
            modifier_niveau_courant(utilisateur=request.user, scolarite=scolarite_a_corriger, niveau=niveau)
            messages.success(request, f"Niveau de {scolarite_a_corriger.annee_scolaire} corrigé.")
            return redirect(_retour_url())

    if request.method == "POST" and request.POST.get("action") == "archiver":
        if not direction:
            raise Http404
        archiver(utilisateur=request.user, eleve=eleve, classe=eleve.classe)
        messages.success(request, f"{eleve.prenom} a été archivé sans supprimer son parcours.")
        return redirect(_retour_url())

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
            "scolarite_a_corriger": scolarite_a_corriger,
            "ariane": ariane,
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
        if (scolarite.bilans.exists() or scolarite.traces.exists() or scolarite.eleveapprentissage_set.exists()
                or scolarite.elevecompetenceselectionnee_set.exists()):
            messages.error(
                request,
                f"{scolarite.eleve.prenom} a des bilans, des compétences suivies ou des observations "
                f"datées enregistrés pour {classe.annee_scolaire} : "
                "utilisez plutôt « Déplacer vers une autre classe », ou "
                "utilisez « Archiver l’élève » pour conserver son parcours.",
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
            f"{eleve.prenom} a été archivé sans supprimer son parcours.",
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
            f"{resultat['crees']} élève(s) ajouté(s) à {classe}. "
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
                        "saisie_bilan": request.POST,
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
            "saisie_bilan": request.POST if request.method == "POST" else None,
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
