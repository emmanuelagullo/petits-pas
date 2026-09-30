"""Contexte des écritures après reprise, sans modifier les origines anciennes."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from suivi.models import (
    AdoptionReferentiel, Classe, EtatAnnuelObservation, ReferentielAnnuel,
    SourceReferentiel, UsageCompetence,
)


@transaction.atomic
def usage_pour_saisie(classe, competence):
    if competence.domaine.ecole_id != classe.ecole_id:
        raise PermissionDenied
    # Écoles non reprises : compatibilité avec l'installation et les ateliers.
    # La bascule automatique de ces parcours relève du jalon d'initialisation.
    source = SourceReferentiel.objects.filter(identifiant=f"reprise-ecole-{classe.ecole_id}", ecole_id=classe.ecole_id).first()
    if source is None:
        return None
    Classe.objects.select_for_update().get(pk=classe.pk)
    adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).first()
    if adoption is None:
        version = source.versions.get(numero="initial")
        annuel, _ = ReferentielAnnuel.objects.get_or_create(
            ecole_id=classe.ecole_id, annee_scolaire=classe.annee_scolaire,
            defaults={"version_proposee": version, "origine_reprise": True},
        )
        adoption = AdoptionReferentiel(classe=classe, annuel=annuel, version=annuel.version_proposee)
        adoption.full_clean()
        adoption.save()
    definitions = {f"locale-{c['id']}": c for c in adoption.version.contenu.get("competences", [])}
    cle = f"locale-{competence.pk}"
    definition = definitions.get(cle)
    if not definition or not definition["active"] or not competence.active:
        # Un ajout ou une mise à jour de source devra passer par le parcours
        # d'adoption, pas une modification directe du catalogue en base.
        raise PermissionDenied("Cette compétence n'est pas disponible dans le référentiel de la classe.")
    usage, _ = UsageCompetence.objects.get_or_create(
        adoption=adoption, competence=competence, defaults={"cle_definition": cle})
    usage.full_clean()
    return usage


def enregistrer_etat_annuel(observation, usage):
    if usage is None:
        return
    etat, _ = EtatAnnuelObservation.objects.get_or_create(
        observation=observation, annee_scolaire=usage.adoption.classe.annee_scolaire)
    etat.usage = usage
    etat.statut = observation.statut
    etat.date_observation = observation.date_observation
    etat.connu = True
    etat.full_clean()
    etat.save()
