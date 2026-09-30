"""Ajouts locaux et reprises explicites, sans copie des acquisitions."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import (AdoptionReferentiel, Classe, Competence, CompetenceLocale,
                         DisponibiliteCompetenceLocale, Domaine, Ecole)
from suivi.referentiels import contenu_origine
from suivi.adaptations_referentiels import contenus_ecole
from .choix_bases_referentiels import verifier_annee


def _verrouiller(utilisateur, ecole, annee, classe=None, adoption_attendue=None):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                   classe if classe else ecole):
        raise PermissionDenied
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if classe:
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee:
            raise PermissionDenied
        adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).select_related("version").first()
        if not adoption or adoption.clos:
            raise ValidationError("Choisissez une base pour une classe ouverte avant d'ajouter une compétence.")
        if adoption.pk != adoption_attendue:
            raise ValidationError("La base a changé. Consultez à nouveau les ajouts.")
        return adoption


def catalogue_reprises(*, utilisateur, ecole, annee, classe):
    """Propositions de l'année, et ajouts déjà utilisés dans une classe gérée."""
    if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee or not autorise(
            utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    classes = [c.pk for c in Classe.objects.filter(ecole=ecole, annee_scolaire__lte=annee)
               if autorise(utilisateur, GERER_REFERENTIEL_CLASSE, c)]
    return CompetenceLocale.objects.filter(ecole=ecole).filter(
        Q(disponibilites__annee_scolaire=annee, disponibilites__classe__isnull=True) |
        Q(disponibilites__classe_id__in=classes)).distinct().order_by("pk")


@transaction.atomic
def creer_ajout(*, utilisateur, ecole, annee, domaine_id, libelle, niveau, classe=None, adoption_attendue=None):
    adoption = _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    contenus = [contenu_origine(adoption)] if classe else [c for _, c in contenus_ecole(ecole, annee)]
    domaine = next((d for c in contenus for d in c.get("domaines", []) if d["id"] == domaine_id), None)
    if domaine is None:
        raise ValidationError("Choisissez un domaine de la base consultée.")
    if not isinstance(libelle, str) or not libelle.strip() or len(libelle.strip()) > 300:
        raise ValidationError("Précisez un libellé de 1 à 300 caractères.")
    if niveau not in ("PS", "MS", "GS"):
        raise ValidationError("Choisissez une section.")
    # Un groupe distinct garde son nom lors des changements de base. Réutiliser
    # un Domaine source aurait rendu l'ajout dépendant d'une version particulière.
    nom = "Ajouts — " + domaine["nom"][:191]
    groupe = Domaine.objects.filter(ecole=ecole, code__startswith="ajout-", nom=nom).first()
    if groupe is None:
        groupe = Domaine.objects.create(ecole=ecole, code="ajout-" + uuid4().hex[:14], nom=nom, ordre=domaine["ordre"])
    competence = Competence(domaine=groupe, code="local-" + uuid4().hex[:24], libelle=libelle.strip(), niveau=niveau)
    competence.full_clean()
    competence.save()
    definition = {"domaines": [{"id": groupe.pk, "code": groupe.code, "nom": groupe.nom, "ordre": groupe.ordre}],
        "competences": [{"id": competence.pk, "domaine_id": groupe.pk, "sous_domaine_id": None,
            "code": competence.code, "libelle": competence.libelle, "niveau": niveau, "icone": "", "ordre": 0,
            "active": True, "cle_definition": f"locale-{competence.pk}"}]}
    locale = CompetenceLocale(ecole=ecole, competence=competence, classe_origine=classe,
                             auteur=utilisateur, definition=definition)
    locale.full_clean()
    locale.save()
    choix = DisponibiliteCompetenceLocale(locale=locale, annee_scolaire=annee, classe=classe, auteur=utilisateur)
    choix.full_clean()
    choix.save()
    journaliser(utilisateur, "referentiel.ajout_cree", locale,
                nouvelles={"competence": competence.pk, "classe": classe.pk if classe else None, "annee": annee})
    return locale


@transaction.atomic
def proposer_ajout(*, utilisateur, ecole, annee, locale):
    _verrouiller(utilisateur, ecole, annee)
    if locale.ecole_id != ecole.pk:
        raise PermissionDenied
    choix, nouveau = DisponibiliteCompetenceLocale.objects.get_or_create(locale=locale, annee_scolaire=annee,
        classe=None, defaults={"auteur": utilisateur})
    if nouveau:
        choix.full_clean()
        journaliser(utilisateur, "referentiel.ajout_propose", choix, nouvelles={"annee": annee})
    return choix


@transaction.atomic
def reprendre_ajout(*, utilisateur, ecole, annee, classe, locale, adoption_attendue):
    _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    if not catalogue_reprises(utilisateur=utilisateur, ecole=ecole, annee=annee, classe=classe).filter(pk=locale.pk).exists():
        raise PermissionDenied
    choix, nouveau = DisponibiliteCompetenceLocale.objects.get_or_create(locale=locale, classe=classe,
        defaults={"annee_scolaire": annee, "auteur": utilisateur})
    if nouveau:
        choix.full_clean()
        journaliser(utilisateur, "referentiel.ajout_repris", choix, nouvelles={"annee": annee, "classe": classe.pk})
    return choix
