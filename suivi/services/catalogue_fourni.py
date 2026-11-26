"""Sources versionnées distribuées avec l’application et publication locale."""
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .choix_bases_referentiels import (
    _application_verrouillee, publier_choix_application, verifier_annee,
)
from .import_sources_referentiels import importer_source

# Liste publique explicite, commune à l'interface et au chargement.
REFERENTIELS_DEPART = (
    ("libre", "Démarrer sans compétences prédéfinies", "referentiel/structure-cycle1.yaml"),
    ("trame", "Trame de démarrage Petits Pas — sélection provisoire", "referentiel/trame-cycle1.yaml"),
    ("objectifs", "Cycle 1 — objectifs des programmes", "referentiel/cycle1/objectifs-programmes.yaml"),
    ("etaye", "Cycle 1 — édition étayée", "referentiel/cycle1/cycle1-etaye.yaml"),
    ("classe-exemple", "Référentiel d’exemple de classe", "referentiel/exemples/classe-demonstration.yaml"),
    ("chatdecole", "Cycle 1 — tableaux Chat d’école", "referentiel/chatdecole/tableaux-cycle1.yaml"),
)


def importer_catalogue_fourni():
    return {
        cle: importer_source((Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8"))[0]
        for cle, _, chemin in REFERENTIELS_DEPART
    }


@transaction.atomic
def completer_catalogue_fourni(annee):
    """Ajoute les sources absentes ; conserve les éditions et le défaut autorisés."""
    verifier_annee(annee)
    application = _application_verrouillee(annee)
    autorisees = list(application.versions_autorisees.all()) if application.configure else []
    sources = {version.source_id for version in autorisees}
    fournis = importer_catalogue_fourni()
    ajouts = [version for version in fournis.values() if version.source_id not in sources]
    if ajouts:
        publier_choix_application(
            annee=annee,
            versions_ids=[version.pk for version in (*autorisees, *ajouts)],
            proposee_id=application.version_proposee_id or fournis["objectifs"].pk,
            revision_attendue=application.revision,
        )
    return fournis, len(ajouts)
