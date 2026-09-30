"""Contexte des écritures après reprise, sans modifier les origines anciennes."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from suivi.models import (
    AdoptionReferentiel, Classe, Ecole, EtatAnnuelObservation, ReferentielAnnuel,
    SourceReferentiel, UsageCompetence,
)


@transaction.atomic
def usage_pour_saisie(classe, competence):
    if competence.domaine.ecole_id != classe.ecole_id:
        raise PermissionDenied
    # Écoles non reprises : compatibilité avec l'installation et les ateliers.
    # La bascule automatique de ces parcours relève du jalon d'initialisation.
    source = SourceReferentiel.objects.filter(identifiant=f"reprise-ecole-{classe.ecole_id}", ecole_id=classe.ecole_id).first()
    Ecole.objects.select_for_update().get(pk=classe.ecole_id)
    Classe.objects.select_for_update().get(pk=classe.pk)
    adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).first()
    if adoption is None:
        if source is None:
            return None
        from .choix_bases_referentiels import choix_bases
        choix = choix_bases(classe.ecole, classe.annee_scolaire)
        version = choix.proposee
        if not version or version.source_id != source.pk:
            raise PermissionDenied("Choisissez le référentiel de la classe avant de saisir.")
        annuel, _ = ReferentielAnnuel.objects.get_or_create(
            ecole_id=classe.ecole_id, annee_scolaire=classe.annee_scolaire,
            defaults={"version_proposee": version, "origine_reprise": True},
        )
        adoption = AdoptionReferentiel(classe=classe, annuel=annuel, version=version)
        adoption.full_clean()
        adoption.save()
    if adoption.clos:
        raise PermissionDenied("Les choix de cette classe sont clos.")
    from suivi.referentiels import contenu_adoption
    definitions = {c["id"]: c for c in contenu_adoption(adoption).get("competences", [])}
    definition = definitions.get(competence.pk)
    cle = definition.get("cle_definition", f"locale-{competence.pk}") if definition else ""
    if not definition or not definition["active"]:
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
