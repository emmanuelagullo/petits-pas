"""Choix de départ d'un paquet vide, partagés par navigateur et programme."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from .catalogue_fourni import REFERENTIELS_DEPART, completer_catalogue_fourni
from .versions_sources_ecoles import definir_version_ecole
from .choix_bases_referentiels import (
    _application_verrouillee, choix_bases, enregistrer_choix_ecole, verifier_annee,
)
from .adoption_bases_referentiels import apercu_adoption, adopter_base
from .equipe import attribuer_affectation, activer_classe
from comptes.models import AffectationClasse

@transaction.atomic
def preparer_referentiel(*, utilisateur, ecole, annee, choix):
    """Ne touche aux choix applicatifs que dans la nouvelle installation locale."""
    if not settings.MODE_LOCAL:
        raise ValidationError("Ce démarrage est réservé à une installation locale.")
    if choix not in {cle for cle, _, _ in REFERENTIELS_DEPART}:
        raise ValidationError("Choisissez un référentiel de départ proposé.")
    verifier_annee(annee)
    application = _application_verrouillee(annee)
    # Une politique déjà configurée reste souveraine, même sans école.
    if application.configure:
        raise ValidationError("Des choix de référentiel existent déjà. Faites vérifier cette installation avant de créer l’école.")
    versions, _ = completer_catalogue_fourni(annee)
    version = versions[choix]
    definir_version_ecole(ecole, version)
    choix_effectifs = choix_bases(ecole, annee)
    enregistrer_choix_ecole(utilisateur=utilisateur, ecole=ecole, annee=annee,
        restreindre=False, versions_ids=[], proposee_id=version.pk,
        revisions_attendues=choix_effectifs.revisions)
    return version


@transaction.atomic
def preparer_premiere_classe(*, utilisateur, appartenance, classe, version, selection_manuelle=False):
    attribuer_affectation(utilisateur=utilisateur, classe=classe,
        type=AffectationClasse.RESPONSABLE, appartenance=appartenance)
    apercu = apercu_adoption(utilisateur=utilisateur, classe=classe, version_id=version.pk)
    adopter_base(utilisateur=utilisateur, classe=classe, version_id=version.pk,
        revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
        garde_attendue=apercu["garde"]["empreinte"], initialisee_depuis_ecole=True,
        selection_manuelle=selection_manuelle)
    activer_classe(utilisateur=utilisateur, classe=classe)
