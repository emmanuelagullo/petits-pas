"""Attributions individuelles d'une trace de classe."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from suivi.audit import journaliser
from suivi.autorisations import CONTRIBUER, MODIFIER_ETAT, autorise
from suivi.models import Observation, Scolarite, Trace, TraceCommune, bornes_annee_scolaire


def personnaliser_texte(texte, prenom):
    return texte.replace("<prénom>", prenom).replace("<prenom>", prenom).replace("{prenom}", prenom)


def _scolarites(classe, ids):
    identifiants = {int(pk) for pk in ids}
    selection = list(Scolarite.objects.select_related("eleve").filter(
        classe=classe, annee_scolaire=classe.annee_scolaire,
        eleve_id__in=identifiants, eleve__ecole=classe.ecole,
        eleve__archive_le__isnull=True,
    ))
    if len(selection) != len(identifiants) or not selection:
        raise ValidationError("Sélectionnez des élèves de cette classe.")
    return selection


@transaction.atomic
def enregistrer_commune(*, utilisateur, classe, competence, ids, valeurs, commune=None):
    if competence.domaine.ecole_id != classe.ecole_id:
        raise PermissionDenied
    date_observation = valeurs.get("date_observation", commune.date_observation if commune else timezone.localdate())
    debut, fin = bornes_annee_scolaire(classe.annee_scolaire)
    if not debut <= date_observation <= fin:
        raise ValidationError("La date doit appartenir à l'année scolaire de la classe.")
    selection = _scolarites(classe, ids)
    if not autorise(utilisateur, MODIFIER_ETAT, classe) or any(
        not autorise(utilisateur, CONTRIBUER, sc.classe) for sc in selection
    ):
        raise PermissionDenied
    if commune is not None:
        commune = TraceCommune.objects.select_for_update().get(pk=commune.pk)
        if commune.classe_id != classe.pk or commune.competence_id != competence.pk or commune.supprime_le:
            raise PermissionDenied
        if not (autorise(utilisateur, MODIFIER_ETAT, classe) or commune.auteur_id == utilisateur.pk):
            raise PermissionDenied
    else:
        commune = TraceCommune(classe=classe, competence=competence, auteur=utilisateur)
    anciens_ids = list(commune.attributions.filter(supprime_le__isnull=True).values_list(
        "observation__eleve_id", flat=True
    )) if commune.pk else []
    communes_ids = {sc.eleve_id for sc in selection}
    if commune.pk and Trace.objects.filter(origine_commune=commune, supprime_le__isnull=True,
                                           observation__eleve_id__in=communes_ids).exists():
        raise ValidationError("Une version personnelle existe : retirez-la avant de réassocier cet élève.")
    for champ in ("date_observation", "commentaire", "photo"):
        if champ in valeurs:
            setattr(commune, champ, valeurs[champ])
    commune.dernier_editeur = utilisateur
    commune.save()
    anciennes = list(commune.attributions.filter(supprime_le__isnull=True))
    for trace in anciennes:
        if trace.observation.eleve_id not in communes_ids:
            trace.supprime_le = timezone.now()
            trace.supprime_par = utilisateur
            trace.save(update_fields=["supprime_le", "supprime_par", "modifie_le"])
    for sc in selection:
        observation, _ = Observation.objects.get_or_create(
            eleve=sc.eleve, competence=competence, defaults={"statut": None}
        )
        trace = commune.attributions.filter(observation=observation, scolarite=sc).first()
        if trace is None:
            trace = Trace(observation=observation, scolarite=sc, commune=commune,
                          auteur=utilisateur)
        trace.date_observation = commune.date_observation
        trace.commentaire = personnaliser_texte(commune.commentaire, sc.eleve.prenom)
        trace.photo = commune.photo.name if commune.photo else None
        trace.supprime_le = None
        trace.supprime_par = None
        trace.dernier_editeur = utilisateur
        trace.save()
    journaliser(utilisateur, "trace_commune.enregistree", commune,
               anciennes={"eleves": sorted(anciens_ids)},
               nouvelles={"eleves": sorted(communes_ids)})
    return commune


@transaction.atomic
def personnaliser(*, utilisateur, trace):
    if trace.commune_id:
        TraceCommune.objects.select_for_update().get(pk=trace.commune_id)
    trace = Trace.objects.select_for_update().select_related(
        "commune", "scolarite__classe"
    ).get(pk=trace.pk)
    if not trace.commune_id or trace.supprime_le or not (
        autorise(utilisateur, MODIFIER_ETAT, trace.scolarite.classe)
        or (trace.auteur_id == utilisateur.pk and autorise(utilisateur, CONTRIBUER, trace.scolarite.classe))
    ):
        raise PermissionDenied
    trace.origine_commune = trace.commune
    trace.commune = None
    trace.dernier_editeur = utilisateur
    trace.save(update_fields=["commune", "origine_commune", "dernier_editeur", "modifie_le"])
    journaliser(utilisateur, "trace_commune.personnalisee", trace,
               nouvelles={"origine_commune": trace.origine_commune_id})
    return trace


@transaction.atomic
def supprimer_commune(*, utilisateur, commune):
    commune = TraceCommune.objects.select_for_update().get(pk=commune.pk)
    if not autorise(utilisateur, MODIFIER_ETAT, commune.classe) or commune.supprime_le:
        raise PermissionDenied
    commune.supprime_le = timezone.now()
    commune.save(update_fields=["supprime_le", "modifie_le"])
    commune.attributions.filter(supprime_le__isnull=True).update(
        supprime_le=commune.supprime_le, supprime_par=utilisateur
    )
    journaliser(utilisateur, "trace_commune.supprimee", commune)
