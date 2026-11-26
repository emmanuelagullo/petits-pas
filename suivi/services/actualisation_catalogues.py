"""Actualisation des éditions déjà reçues, dans leur périmètre d’import."""
from django.core.exceptions import ValidationError
from django.db import transaction

from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.identites_referentiels import identifiant_source_classe, identifiant_source_ecole
from suivi.models import Classe, Ecole, SourceReferentiel

from .catalogues_externes import edition_grist, identite_grist, lire_catalogue_grist, reglages_catalogues_classe
from .import_sources_referentiels import importer_source


def actualiser_catalogues_classe(utilisateur, classe):
    if classe.etat != Classe.ACTIVE or not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        return 0, []
    nombre, erreurs = 0, []
    regles = reglages_catalogues_classe(classe)
    for url, reglage in regles.items():
        if not reglage.get("suivre_catalogue") or not reglage.get("catalogue", {}).get("url"):
            continue
        try:
            catalogue = lire_catalogue_grist(url)
            if catalogue["url"] != url:
                raise ValidationError("L’adresse du catalogue a changé.")
            nombre += actualiser_editions_connues(utilisateur, classe, catalogue)
        except ValidationError as erreur:
            erreurs.append(f'{reglage["catalogue"]["nom"]} — {" ".join(erreur.messages)}')
    return nombre, erreurs


def actualiser_editions_connues(utilisateur, classe, catalogue):
    nombre = 0
    ecole = classe.ecole
    pour_ecole = autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole)
    for referentiel in catalogue["referentiels"]:
        reference = referentiel["reference"]
        numero = max(referentiel["editions"])
        identifiant = identite_grist(catalogue["url"], reference)
        source_classe = identifiant_source_classe(classe, identifiant)
        source_ecole = identifiant_source_ecole(ecole, identifiant)
        sources = SourceReferentiel.objects.filter(ecole=ecole, identifiant__in=[source_classe, source_ecole]).in_bulk(
            field_name="identifiant",
        )
        source = sources.get(source_classe) or (sources.get(source_ecole) if pour_ecole else None)
        if not source or source.versions.filter(numero=str(numero)).exists():
            continue
        document = edition_grist(catalogue["url"], reference, numero)
        with transaction.atomic():
            ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
            classe = Classe.objects.select_for_update().select_related("ecole").get(pk=classe.pk)
            reglage = reglages_catalogues_classe(classe).get(catalogue["url"], {})
            if (classe.etat != Classe.ACTIVE or not reglage.get("suivre_catalogue")
                    or not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe)
                    or (not source.classe_privee_id and not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole))):
                continue
            _, cree, _ = importer_source(document, ecole=ecole, classe=classe if source.classe_privee_id else None)
            nombre += cree
    return nombre
