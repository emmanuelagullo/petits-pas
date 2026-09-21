from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from suivi.audit import instantane, journaliser
from suivi.autorisations import CONTRIBUER, MODIFIER_ETAT, autorise
from suivi.models import Bilan, Observation, Trace


CHAMPS_TRACE = (
    "date_observation",
    "commentaire",
    "photo",
    "visible_carnet",
    "supprime_le",
)
CHAMPS_BILAN = ("date_bilan", "texte", "visible_carnet", "supprime_le")


def _est_responsable(utilisateur, classe):
    return autorise(utilisateur, MODIFIER_ETAT, classe)


def _peut_corriger_trace(utilisateur, trace):
    classe = trace.scolarite.classe
    return _est_responsable(utilisateur, classe) or (
        trace.auteur_id == utilisateur.pk
        and autorise(utilisateur, CONTRIBUER, classe)
        and classe.etat == classe.ACTIVE
    )


@transaction.atomic
def modifier_etat(*, utilisateur, eleve, competence, statut):
    if not autorise(utilisateur, MODIFIER_ETAT, eleve):
        raise PermissionDenied
    observation = Observation.objects.select_for_update().filter(
        eleve=eleve, competence=competence
    ).first()
    anciennes = {"statut": observation.statut if observation else None}
    if observation is None:
        observation = Observation(eleve=eleve, competence=competence)
    observation.statut = statut
    observation.date_observation = timezone.localdate()
    observation.save()
    journaliser(
        utilisateur,
        "observation.etat_modifie",
        observation,
        anciennes,
        {"statut": statut},
    )
    return observation


@transaction.atomic
def enregistrer_trace(
    *, utilisateur, eleve, competence, scolarite, trace=None, valeurs
):
    if (
        scolarite.eleve_id != eleve.pk
        or competence.domaine.ecole_id != scolarite.classe.ecole_id
        or (
            trace is not None
            and (
                trace.observation.eleve_id != eleve.pk
                or trace.observation.competence_id != competence.pk
                or trace.scolarite_id != scolarite.pk
                or trace.supprime_le is not None
            )
        )
    ):
        raise PermissionDenied
    if not autorise(utilisateur, CONTRIBUER, scolarite.classe):
        raise PermissionDenied
    creation = trace is None
    if trace is not None and not _peut_corriger_trace(utilisateur, trace):
        raise PermissionDenied
    observation, _ = Observation.objects.get_or_create(
        eleve=eleve,
        competence=competence,
        defaults={"statut": None},
    )
    trace = trace or Trace(
        observation=observation,
        scolarite=scolarite,
        auteur=utilisateur,
    )
    if not _est_responsable(utilisateur, scolarite.classe):
        valeurs["visible_carnet"] = trace.visible_carnet if trace.pk else True
    anciennes = {} if creation else instantane(trace, CHAMPS_TRACE)
    for champ, valeur in valeurs.items():
        setattr(trace, champ, valeur)
    trace.dernier_editeur = utilisateur
    trace.save()
    journaliser(
        utilisateur,
        "trace.creee" if creation else "trace.modifiee",
        trace,
        anciennes,
        instantane(trace, CHAMPS_TRACE),
    )
    return trace


@transaction.atomic
def supprimer_trace_logiquement(*, utilisateur, trace):
    if not _peut_corriger_trace(utilisateur, trace):
        raise PermissionDenied
    anciennes = instantane(trace, CHAMPS_TRACE)
    trace.supprime_le = timezone.now()
    trace.supprime_par = utilisateur
    trace.dernier_editeur = utilisateur
    trace.save(
        update_fields=[
            "supprime_le",
            "supprime_par",
            "dernier_editeur",
            "modifie_le",
        ]
    )
    journaliser(
        utilisateur,
        "trace.supprimee",
        trace,
        anciennes,
        instantane(trace, CHAMPS_TRACE),
    )
    return trace


@transaction.atomic
def definir_visibilite_trace(*, utilisateur, trace, visible):
    if not _est_responsable(utilisateur, trace.scolarite.classe):
        raise PermissionDenied
    anciennes = instantane(trace, CHAMPS_TRACE)
    trace.visible_carnet = visible
    trace.dernier_editeur = utilisateur
    trace.save(update_fields=["visible_carnet", "dernier_editeur", "modifie_le"])
    journaliser(
        utilisateur,
        "trace.visibilite_modifiee",
        trace,
        anciennes,
        instantane(trace, CHAMPS_TRACE),
    )
    return trace


@transaction.atomic
def restaurer_trace(*, utilisateur, trace):
    if not _est_responsable(utilisateur, trace.scolarite.classe):
        raise PermissionDenied
    anciennes = instantane(trace, CHAMPS_TRACE)
    trace.supprime_le = None
    trace.supprime_par = None
    trace.dernier_editeur = utilisateur
    trace.save(
        update_fields=[
            "supprime_le",
            "supprime_par",
            "dernier_editeur",
            "modifie_le",
        ]
    )
    journaliser(
        utilisateur,
        "trace.restauree",
        trace,
        anciennes,
        instantane(trace, CHAMPS_TRACE),
    )
    return trace


@transaction.atomic
def enregistrer_bilan(*, utilisateur, bilan=None, valeurs):
    scolarite = valeurs.get("scolarite") or bilan.scolarite
    if not autorise(utilisateur, MODIFIER_ETAT, scolarite.classe):
        raise PermissionDenied
    creation = bilan is None
    bilan = bilan or Bilan(auteur=utilisateur)
    anciennes = {} if creation else instantane(bilan, CHAMPS_BILAN)
    for champ, valeur in valeurs.items():
        setattr(bilan, champ, valeur)
    bilan.dernier_editeur = utilisateur
    bilan.save()
    journaliser(
        utilisateur,
        "bilan.cree" if creation else "bilan.modifie",
        bilan,
        anciennes,
        instantane(bilan, CHAMPS_BILAN),
    )
    return bilan


@transaction.atomic
def supprimer_bilan_logiquement(*, utilisateur, bilan):
    if not _est_responsable(utilisateur, bilan.scolarite.classe):
        raise PermissionDenied
    anciennes = instantane(bilan, CHAMPS_BILAN)
    bilan.supprime_le = timezone.now()
    bilan.supprime_par = utilisateur
    bilan.dernier_editeur = utilisateur
    bilan.save(
        update_fields=[
            "supprime_le",
            "supprime_par",
            "dernier_editeur",
            "modifie_le",
        ]
    )
    journaliser(
        utilisateur,
        "bilan.supprime",
        bilan,
        anciennes,
        instantane(bilan, CHAMPS_BILAN),
    )
    return bilan


@transaction.atomic
def definir_visibilite_bilan(*, utilisateur, bilan, visible):
    if not _est_responsable(utilisateur, bilan.scolarite.classe):
        raise PermissionDenied
    anciennes = instantane(bilan, CHAMPS_BILAN)
    bilan.visible_carnet = visible
    bilan.dernier_editeur = utilisateur
    bilan.save(update_fields=["visible_carnet", "dernier_editeur", "modifie_le"])
    journaliser(
        utilisateur,
        "bilan.visibilite_modifiee",
        bilan,
        anciennes,
        instantane(bilan, CHAMPS_BILAN),
    )
    return bilan
