"""Application du 2FA aux requêtes : second facteur à la connexion, échéance
d'inscription pour les comptes soumis à l'obligation, bandeau de rappel.

Un compte inscrit (et dont la fonction n'est pas désactivée) n'obtient jamais
de session sans avoir passé le second facteur : la connexion s'arrête avant
login() tant qu'il manque. Le middleware ferme aussi la porte aux sessions
nées d'un autre chemin. Sans la fonction (dépendances ou clé absentes, mode
local), rien de tout cela ne s'exécute.
"""
import math
import time
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.shortcuts import redirect
from django.utils import timezone

from comptes.models import DoubleFacteurCompte

from .double_facteur import Exigence, exigence_double_facteur

SESSION_VERIFIE = "double_facteur_verifie"
SESSION_ATTENTE = "double_facteur_attente"
SESSION_EXIGENCE = "double_facteur_exigence"
DELAI_ATTENTE_SECONDES = 300
SESSION_CONNEXION_LE = "connexion_le"
# Au-delà, lier un premier appareil redemande le mot de passe (une session
# volée ne doit pas pouvoir enrôler son propre authentificateur).
CONNEXION_RECENTE_SECONDES = 300
# Pages restant accessibles à un compte qui doit encore s'inscrire.
PAGES_INSCRIPTION = {"double_facteur", "deconnexion"}


@dataclass(frozen=True)
class EtatAcces:
    action: str  # "libre", "verifier" ou "inscrire"
    jours_restants: int | None = None


def disponible():
    return settings.DOUBLE_FACTEUR_DISPONIBLE


def _exigence_en_cache(request):
    """Exigence du compte, recalculée au plus toutes les quelques secondes."""
    duree = settings.DOUBLE_FACTEUR_CACHE_SECONDES
    maintenant = time.time()
    memorisee = request.session.get(SESSION_EXIGENCE)
    if duree and memorisee and maintenant - memorisee[1] < duree:
        return Exigence(memorisee[0])
    exigence = exigence_double_facteur(request.user)
    request.session[SESSION_EXIGENCE] = [exigence.value, maintenant]
    return exigence


def verification_requise_a_la_connexion(utilisateur):
    """Vrai si ce compte doit passer le second facteur avant d'être connecté."""
    if not disponible():
        return False
    compte = DoubleFacteurCompte.objects.filter(utilisateur=utilisateur).first()
    return bool(
        compte and compte.inscrit
        and exigence_double_facteur(utilisateur) != Exigence.DESACTIVEE
    )


def poser_echeance_si_besoin(utilisateur, *, delai_de_grace=True):
    """Compte devenu soumis à l'obligation : date d'échéance de l'inscription.

    Un compte neuf n'a pas de délai de grâce (inscription dès sa création) ;
    un compte existant en a un, à partir du premier constat de l'obligation.
    """
    if not disponible() or exigence_double_facteur(utilisateur) != Exigence.OBLIGATOIRE:
        return
    compte, _ = DoubleFacteurCompte.objects.get_or_create(utilisateur=utilisateur)
    if compte.inscrit:
        return
    if compte.echeance_le is not None:
        # Une promotion ou récupération sans grâce ne conserve pas le délai
        # qui avait été accordé pour une fonction précédente.
        if not delai_de_grace and compte.echeance_le > timezone.now():
            compte.echeance_le = timezone.now()
            compte.save(update_fields=["echeance_le"])
        return
    jours = settings.DOUBLE_FACTEUR_DELAI_GRACE_JOURS if delai_de_grace else 0
    compte.echeance_le = timezone.now() + timedelta(days=jours)
    compte.save(update_fields=["echeance_le"])


def evaluer(request):
    if not disponible() or not request.user.is_authenticated:
        return EtatAcces("libre")
    exigence = _exigence_en_cache(request)
    if exigence == Exigence.DESACTIVEE:
        return EtatAcces("libre")
    compte = DoubleFacteurCompte.objects.filter(utilisateur=request.user).first()
    if compte is not None and compte.inscrit:
        verifie = request.session.get(SESSION_VERIFIE)
        return EtatAcces("libre" if verifie else "verifier")
    if exigence == Exigence.OPTIONNELLE:
        if compte is not None and compte.echeance_le is not None:
            compte.echeance_le = None
            compte.save(update_fields=["echeance_le"])
        return EtatAcces("libre")
    poser_echeance_si_besoin(request.user)
    compte = DoubleFacteurCompte.objects.get(utilisateur=request.user)
    reste = compte.echeance_le - timezone.now()
    if reste <= timedelta(0):
        return EtatAcces("inscrire")
    return EtatAcces("libre", max(1, math.ceil(reste.total_seconds() / 86400)))


class DoubleFacteurMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.resolver_match and request.resolver_match.url_name == "maintenance_annonce":
            return None
        if not disponible() or not request.user.is_authenticated:
            return None
        etat = evaluer(request)
        request.double_facteur_jours_restants = etat.jours_restants
        if etat.action == "verifier":
            # Session née sans second facteur : on la ferme.
            logout(request)
            return redirect("connexion")
        if etat.action == "inscrire":
            nom = request.resolver_match.url_name if request.resolver_match else None
            if nom not in PAGES_INSCRIPTION:
                messages.warning(
                    request,
                    "Votre fonction exige l'authentification à deux facteurs. "
                    "Configurez-la pour continuer.",
                )
                return redirect("double_facteur")
        return None


@receiver(user_logged_in)
def _noter_la_connexion(sender, request=None, **kwargs):
    if request is not None and hasattr(request, "session"):
        noter_authentification(request)


def noter_authentification(request):
    request.session[SESSION_CONNEXION_LE] = int(time.time())


def connexion_recente(request):
    """Vrai si le mot de passe a été saisi pour cette session il y a peu.

    Une session sans horodatage (antérieure à ce contrôle) n'est pas récente :
    le mot de passe est demandé une fois.
    """
    depuis = request.session.get(SESSION_CONNEXION_LE)
    return (
        isinstance(depuis, int)
        and 0 <= time.time() - depuis <= CONNEXION_RECENTE_SECONDES
    )


def fermer_sessions_compte(utilisateur):
    """Une promotion sensible exige une nouvelle connexion (sessions DB).

    Le déploiement utilise les sessions Django en base. La suppression évite
    qu'une exigence mise en cache avant la promotion garde un délai de grâce.
    """
    from django.contrib.sessions.models import Session

    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(utilisateur.pk):
            session.delete()
