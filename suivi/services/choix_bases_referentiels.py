"""Autorisations et défauts annuels ; aucune adoption implicite d'une classe."""
from dataclasses import dataclass
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import (AdoptionReferentiel, ChoixApplicationAnnuel, ChoixEcoleAnnuel,
                          Ecole, VersionReferentiel)


@dataclass(frozen=True)
class ChoixBases:
    versions: tuple
    proposee: object
    revision_application: int
    revision_ecole: int
    avertissements: tuple

    @property
    def revisions(self):
        return (self.revision_application, self.revision_ecole)


def verifier_annee(annee):
    if not isinstance(annee, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{4}", annee):
        raise ValidationError("Préciser une année scolaire, par exemple 2026-2027.")
    debut = int(annee[:4])
    if debut < 1900 or int(annee[5:]) != debut + 1:
        raise ValidationError("L'année scolaire doit couvrir deux années consécutives.")


def _superieur(ecole, annee, application):
    if application and application.configure:
        ids = application.versions_autorisees.values_list("pk", flat=True)
        # Les seules versions fournies sont les versions explicitement publiées.
        versions = list(VersionReferentiel.objects.filter(pk__in=ids, source__ecole__isnull=True,
            contenu__origine="source_declaree").select_related("source").order_by("source__titre", "pk"))
        return versions, application.version_proposee_id
    # Compatibilité : une base locale reprise ne devient pas une source nationale.
    initiale = VersionReferentiel.objects.filter(source__ecole=ecole,
        source__identifiant=f"reprise-ecole-{ecole.pk}", numero="initial").select_related("source").first()
    return ([initiale], initiale.pk) if initiale else ([], None)


def choix_bases(ecole, annee):
    verifier_annee(annee)
    application = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    local = ChoixEcoleAnnuel.objects.filter(ecole=ecole, annee_scolaire=annee).first()
    versions, proposee_id = _superieur(ecole, annee, application)
    avertissements = []
    if local:
        if local.restreindre:
            explicites = set(local.versions_autorisees.values_list("pk", flat=True))
            superieurs = {v.pk for v in versions}
            if explicites - superieurs:
                avertissements.append("Certaines bases choisies par l'école ne sont plus autorisées par l'application.")
            versions = [v for v in versions if v.pk in explicites]
        if local.version_proposee_id is not None:
            proposee_id = local.version_proposee_id
    proposee = next((v for v in versions if v.pk == proposee_id), None)
    if proposee_id is not None and proposee is None:
        avertissements.append("La base proposée n'est plus autorisée. Choisissez une autre base proposée ; aucun remplacement automatique n'est effectué.")
    autorisees = {v.pk for v in versions}
    if AdoptionReferentiel.objects.filter(classe__ecole=ecole, classe__annee_scolaire=annee,
                                         courante=True).exclude(version_id__in=autorisees).exists():
        avertissements.append("Des classes utilisent une base qui n'est plus autorisée pour les nouveaux choix. Leur base et leurs observations sont conservées.")
    return ChoixBases(tuple(versions), proposee, application.revision if application else 0,
                     local.revision if local else 0, tuple(avertissements))


def _application_verrouillee(annee):
    ChoixApplicationAnnuel.objects.get_or_create(annee_scolaire=annee)
    return ChoixApplicationAnnuel.objects.select_for_update().get(annee_scolaire=annee)


def _ids(valeurs):
    try:
        resultat = set(valeurs)
    except TypeError as erreur:
        raise ValidationError("La liste des bases est invalide.") from erreur
    if any(type(v) is not int or v <= 0 for v in resultat):
        raise ValidationError("Les identifiants de version doivent être des nombres entiers positifs.")
    return resultat


def _revision(valeur):
    if type(valeur) is not int or valeur < 0:
        raise ValidationError("La révision attendue doit être un entier positif ou nul.")


def _defaut(autorisees, proposee_id):
    if proposee_id is not None and (type(proposee_id) is not int or proposee_id not in autorisees):
        raise ValidationError("Le choix proposé par défaut doit être une base autorisée.")


@transaction.atomic
def publier_choix_application(*, annee, versions_ids, proposee_id, revision_attendue):
    """Opération d'administration du déploiement, exposée seulement en commande."""
    verifier_annee(annee)
    _revision(revision_attendue)
    ids = _ids(versions_ids)
    _defaut(ids, proposee_id)
    if ids and proposee_id is None:
        raise ValidationError("Choisissez une base proposée par défaut parmi les bases autorisées.")
    disponibles = set(VersionReferentiel.objects.filter(pk__in=ids, source__ecole__isnull=True,
        contenu__origine="source_declaree").values_list("pk", flat=True))
    if ids != disponibles:
        raise ValidationError("Les choix de l'application doivent être des versions fournies importées au catalogue.")
    application = _application_verrouillee(annee)
    if application.revision != revision_attendue:
        raise ValidationError("Les choix ont changé depuis leur consultation. Relisez-les avant de confirmer.")
    application.configure = True
    application.version_proposee_id = proposee_id
    application.revision += 1
    application.save(update_fields=["configure", "version_proposee", "revision"])
    application.versions_autorisees.set(ids)
    return application


@transaction.atomic
def enregistrer_choix_ecole(*, utilisateur, ecole, annee, restreindre,
                            versions_ids, proposee_id, revisions_attendues, demarrage_attendu=None):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    if type(restreindre) is not bool:
        raise ValidationError("Préciser si l'école conserve une liste de bases autorisées.")
    if not isinstance(revisions_attendues, (tuple, list)) or len(revisions_attendues) != 2:
        raise ValidationError("Préciser les révisions consultées de l'application et de l'école.")
    for revision in revisions_attendues:
        _revision(revision)
    ids = _ids(versions_ids)
    if not restreindre and ids:
        raise ValidationError("Pour garder les autorisations proposées, ne transmettez pas de liste locale.")
    application = _application_verrouillee(annee)
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if demarrage_attendu is not None:
        from .garde_fous_referentiels import demarrage_ecole
        if demarrage_ecole(ecole) != demarrage_attendu:
            raise ValidationError("La préparation de l'école a évolué. Consultez un nouvel aperçu.")
    local, _ = ChoixEcoleAnnuel.objects.get_or_create(ecole=ecole, annee_scolaire=annee)
    local = ChoixEcoleAnnuel.objects.select_for_update().get(pk=local.pk)
    if (application.revision, local.revision) != tuple(revisions_attendues):
        raise ValidationError("Les choix ont changé depuis leur consultation. Relisez-les avant de confirmer.")
    _verifier_choix_ecole(ecole, annee, application, restreindre, ids, proposee_id)
    anciennes = {"restreindre": local.restreindre, "versions": list(local.versions_autorisees.values_list("pk", flat=True)),
                 "proposee": local.version_proposee_id, "revision": local.revision}
    local.restreindre = restreindre
    local.version_proposee_id = proposee_id
    local.revision += 1
    local.save(update_fields=["restreindre", "version_proposee", "revision"])
    local.versions_autorisees.set(ids)
    journaliser(utilisateur, "referentiel.choix_ecole", local, anciennes=anciennes,
        nouvelles={"restreindre": restreindre, "versions": sorted(ids), "proposee": proposee_id, "revision": local.revision})
    return local


def _verifier_choix_ecole(ecole, annee, application, restreindre, ids, proposee_id):
    versions, superieur_id = _superieur(ecole, annee, application)
    superieurs = {v.pk for v in versions}
    if restreindre and ids - superieurs:
        raise ValidationError("L'école ne peut pas autoriser une base non autorisée par l'application.")
    effectives = ids if restreindre else superieurs
    _defaut(effectives, proposee_id)
    if effectives and proposee_id is None and superieur_id not in effectives:
        raise ValidationError("La base proposée par l'application n'est pas dans votre liste. Choisissez un défaut autorisé.")
    proposee_effective = proposee_id if proposee_id is not None else superieur_id
    return tuple(v for v in versions if v.pk in effectives), next(
        (v for v in versions if v.pk in effectives and v.pk == proposee_effective), None)


def choix_superieurs(ecole, annee):
    """Bases proposées à l'école ; lecture seule, y compris sans configuration."""
    verifier_annee(annee)
    application = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    versions, proposee_id = _superieur(ecole, annee, application)
    return tuple(versions), next((v for v in versions if v.pk == proposee_id), None)


def apercu_choix_ecole(*, utilisateur, ecole, annee, restreindre, versions_ids, proposee_id):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    if type(restreindre) is not bool:
        raise ValidationError("Préciser si l'école conserve une liste de bases autorisées.")
    ids = _ids(versions_ids)
    if not restreindre and ids:
        raise ValidationError("Pour garder les autorisations proposées, ne transmettez pas de liste locale.")
    application = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    local = ChoixEcoleAnnuel.objects.filter(ecole=ecole, annee_scolaire=annee).first()
    versions, proposee = _verifier_choix_ecole(ecole, annee, application, restreindre, ids, proposee_id)
    conservees = AdoptionReferentiel.objects.filter(classe__ecole=ecole,
        classe__annee_scolaire=annee, courante=True).exclude(
        version_id__in=[v.pk for v in versions]).select_related("classe", "version__source").order_by("classe__nom", "pk")
    return {"versions": versions, "proposee": proposee, "revisions": (application.revision if application else 0, local.revision if local else 0),
            "restreindre": restreindre, "versions_ids": sorted(ids), "proposee_id": proposee_id,
            "classes_conservees": list(conservees)}
