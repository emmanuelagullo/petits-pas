"""Premier choix de base avec confirmation ; transition après saisies à venir."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, autorise
from suivi.models import (AdoptionReferentiel, Classe, CompetenceSourceEcole, Ecole, Observation,
                         ReferentielAnnuel, UsageCompetence, Trace, TraceCommune)
from suivi.referentiels import contenu_adoption
from .choix_bases_referentiels import _application_verrouillee, choix_bases
from .versions_sources_ecoles import definir_version_ecole


def apercu_adoption(*, utilisateur, classe, version_id):
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    choix = choix_bases(classe.ecole, classe.annee_scolaire)
    version = next((v for v in choix.versions if v.pk == version_id), None)
    if version is None:
        raise ValidationError("Cette base n'est pas autorisée pour la classe.")
    actuelle = AdoptionReferentiel.objects.filter(classe=classe, courante=True).select_related("version").first()
    if actuelle and actuelle.clos:
        raise ValidationError("Les choix de cette classe sont clos.")
    if actuelle and actuelle.version_id == version_id:
        nouveaux_ids = {c["id"] for c in contenu_adoption(actuelle).get("competences", [])}
        nombre = len(nouveaux_ids)
    elif version.source.ecole_id is not None:
        nouveaux_ids = {c["id"] for c in version.contenu.get("competences", [])}
        nombre = len(nouveaux_ids)
    else:
        nouveaux_ids = set(CompetenceSourceEcole.objects.filter(ecole=classe.ecole,
            identite__definitions__version=version).values_list("competence_id", flat=True))
        nombre = version.definitions.count()
    anciens_ids = {c["id"] for c in contenu_adoption(actuelle).get("competences", [])} if actuelle else set()
    meme = bool(actuelle and actuelle.version_id == version_id)
    # Les transitions renseignées nécessitent le lecteur de toutes les adoptions
    # et une conservation finale complète. Ne pas les ouvrir partiellement.
    renseignee = (Observation.objects.filter(eleve__scolarites__classe=classe).exists()
                  or Trace.objects.filter(usage_referentiel__adoption__classe=classe).exists()
                  or TraceCommune.objects.filter(classe=classe).exists())
    return {"version": version, "adoption_id": actuelle.pk if actuelle else None,
            "revisions": choix.revisions, "communes": len(anciens_ids & nouveaux_ids),
            "nouvelles": nombre - len(anciens_ids & nouveaux_ids),
            "hors_base": len(anciens_ids - nouveaux_ids), "meme": meme,
            "bloquee": renseignee and not meme}


@transaction.atomic
def adopter_base(*, utilisateur, classe, version_id, revisions_attendues, adoption_attendue):
    classe_fournie = classe
    # Même ordre de coordination que les choix d'école.
    _application_verrouillee(classe.annee_scolaire)
    Ecole.objects.select_for_update().get(pk=classe.ecole_id)
    classe = Classe.objects.select_for_update().select_related("ecole").get(pk=classe.pk)
    apercu = apercu_adoption(utilisateur=utilisateur, classe=classe, version_id=version_id)
    if apercu["revisions"] != tuple(revisions_attendues) or apercu["adoption_id"] != adoption_attendue:
        raise ValidationError("Les choix ont changé. Consultez à nouveau l'aperçu avant de confirmer.")
    if apercu["bloquee"]:
        raise ValidationError("Cette classe comporte déjà des observations. Le changement de base après saisie n'est pas encore disponible ; son suivi reste conservé.")
    if apercu["meme"]:
        return AdoptionReferentiel.objects.get(pk=apercu["adoption_id"])
    version = apercu["version"]
    contenu = definir_version_ecole(classe.ecole, version)
    annuel, _ = ReferentielAnnuel.objects.get_or_create(ecole=classe.ecole, annee_scolaire=classe.annee_scolaire,
                                                      defaults={"version_proposee": version})
    AdoptionReferentiel.objects.filter(classe=classe, courante=True).update(courante=False)
    adoption = AdoptionReferentiel(classe=classe, annuel=annuel, version=version, contenu=contenu,
                                   auteur=utilisateur, adopte_le=timezone.now())
    adoption.full_clean()
    adoption.save()
    for c in contenu["competences"]:
        usage = UsageCompetence(adoption=adoption, competence_id=c["id"], cle_definition=c.get("cle_definition", f"locale-{c['id']}"))
        usage.full_clean()
        usage.save()
    journaliser(utilisateur, "referentiel.base_classe", adoption,
        anciennes={"adoption": apercu["adoption_id"]}, nouvelles={"version": version.pk})
    classe_fournie._adoption_referentiel_lecture = adoption
    return adoption
