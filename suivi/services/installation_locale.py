"""Choix de départ d'un paquet vide, partagés par navigateur et programme."""
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from suivi.models import ChoixApplicationAnnuel
from .import_sources_referentiels import importer_source
from .choix_bases_referentiels import (
    choix_bases, publier_choix_application, enregistrer_choix_ecole,
)
from .adoption_bases_referentiels import apercu_adoption, adopter_base
from .equipe import attribuer_affectation, activer_classe
from comptes.models import AffectationClasse

# Liste publique explicite, commune à l'interface et au chargement.
REFERENTIELS_DEPART = (
    ("trame", "Trame de démarrage Petits Pas — sélection provisoire", None),
    ("objectifs", "Cycle 1 — objectifs des programmes (2026.1)", "referentiel/cycle1/objectifs-programmes.yaml"),
    ("etaye", "Cycle 1 — édition étayée (2026.2)", "referentiel/cycle1/cycle1-etaye.yaml"),
    ("chatdecole", "Cycle 1 — tableaux Chat d’école", "referentiel/chatdecole/tableaux-cycle1.yaml"),
)


@transaction.atomic
def preparer_referentiel(*, utilisateur, ecole, annee, choix):
    """Ne touche aux choix applicatifs que dans la nouvelle installation locale."""
    if not settings.MODE_LOCAL:
        raise ValidationError("Ce démarrage est réservé à une installation locale.")
    if choix not in {cle for cle, _, _ in REFERENTIELS_DEPART}:
        raise ValidationError("Choisissez un référentiel de départ proposé.")
    from .choix_bases_referentiels import verifier_annee
    verifier_annee(annee)
    application = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    # Une politique déjà configurée reste souveraine, même sans école.
    if application and application.configure:
        raise ValidationError("Des choix de référentiel existent déjà. Faites vérifier cette installation avant de créer l’école.")
    if choix == "trame":
        version = choix_bases(ecole, annee).proposee
    else:
        versions = {}
        for cle, _, chemin in REFERENTIELS_DEPART:
            if chemin:
                version, _, _ = importer_source((Path(settings.BASE_DIR) / chemin).read_text())
                versions[cle] = version
        version = versions[choix]
        # Le choix de départ ne restreint pas les autres bases fournies.
        publier_choix_application(annee=annee, versions_ids=[v.pk for v in versions.values()],
            proposee_id=versions["objectifs"].pk, revision_attendue=application.revision if application else 0)
    choix_effectifs = choix_bases(ecole, annee)
    enregistrer_choix_ecole(utilisateur=utilisateur, ecole=ecole, annee=annee,
        restreindre=False, versions_ids=[], proposee_id=version.pk,
        revisions_attendues=choix_effectifs.revisions)
    return version


@transaction.atomic
def preparer_premiere_classe(*, utilisateur, appartenance, classe, version):
    attribuer_affectation(utilisateur=utilisateur, classe=classe,
        type=AffectationClasse.RESPONSABLE, appartenance=appartenance)
    apercu = apercu_adoption(utilisateur=utilisateur, classe=classe, version_id=version.pk)
    adopter_base(utilisateur=utilisateur, classe=classe, version_id=version.pk,
        revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
        garde_attendue=apercu["garde"]["empreinte"], initialisee_depuis_ecole=True)
    activer_classe(utilisateur=utilisateur, classe=classe)
