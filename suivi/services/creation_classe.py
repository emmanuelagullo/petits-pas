"""Créer la classe et son premier choix atomiquement ; aucun remplacement."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.autorisations import GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import Classe, Ecole
from .choix_bases_referentiels import _application_verrouillee, choix_bases, verifier_annee
from .adoption_bases_referentiels import adopter_base, apercu_adoption


@transaction.atomic
def creer_classe_avec_base(*, utilisateur, ecole, nom, annee, base, revisions_attendues):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    _application_verrouillee(annee)
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    choix = choix_bases(ecole, annee)
    if choix.revisions != tuple(revisions_attendues):
        raise ValidationError("Les propositions ont changé. Vérifiez le référentiel affiché avant de créer la classe.")
    depuis_ecole = base == "ecole"
    if depuis_ecole:
        version = choix.proposee
        if not version:
            raise ValidationError("Aucun référentiel n'est proposé pour cette année.")
    elif base == "plus_tard":
        if choix.proposee:
            raise ValidationError("Utilisez la proposition de l'école ou choisissez une autre base.")
        version = None
    else:
        version = next((v for v in choix.versions if str(v.pk) == base), None)
        if not version:
            raise ValidationError("Cette base n'est pas autorisée pour cette année.")
    classe, creee = Classe.objects.get_or_create(ecole=ecole, nom=nom, annee_scolaire=annee)
    if not creee:
        raise ValidationError("Cette classe existe déjà pour cette année.")
    if version:
        apercu = apercu_adoption(utilisateur=utilisateur, classe=classe, version_id=version.pk)
        adopter_base(utilisateur=utilisateur, classe=classe, version_id=version.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=None,
            garde_attendue=apercu["garde"]["empreinte"], initialisee_depuis_ecole=depuis_ecole)
    return classe
