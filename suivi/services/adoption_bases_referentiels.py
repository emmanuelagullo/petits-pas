"""Choix daté de base avec aperçu et confirmation, sans transfert des acquis."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, autorise
from suivi.models import (AdoptionReferentiel, Classe, CompetenceSourceEcole, Ecole,
                         ReferentielAnnuel, UsageCompetence)
from suivi.referentiels import contenu_adoption
from .choix_bases_referentiels import _application_verrouillee, choix_bases
from .versions_sources_ecoles import definir_version_ecole
from .apercu_mises_a_jour import apercu_mise_a_jour
from .garde_fous_referentiels import garde_adoption, consommer_permission


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
    from suivi.models import DisponibiliteCompetenceLocale
    locaux = set(DisponibiliteCompetenceLocale.objects.filter(classe=classe).values_list("locale__competence_id", flat=True))
    if actuelle and actuelle.version_id == version_id:
        nouveaux_ids = {c["id"] for c in contenu_adoption(actuelle).get("competences", [])}
        nouveaux_ids -= locaux
        nombre = len(nouveaux_ids)
    elif version.source.ecole_id is not None:
        nouveaux_ids = {c["id"] for c in version.contenu.get("competences", [])}
        nouveaux_ids -= locaux
        nombre = len(nouveaux_ids)
    else:
        nouveaux_ids = set(CompetenceSourceEcole.objects.filter(ecole=classe.ecole,
            identite__definitions__version=version).values_list("competence_id", flat=True))
        nombre = version.definitions.count()
    anciens_ids = {c["id"] for c in contenu_adoption(actuelle).get("competences", [])} if actuelle else set()
    anciens_ids -= locaux
    from suivi.correspondances_referentiels import correspondances_classe
    liens = [l for l in correspondances_classe(classe) if
        (l["depart_id"] in nouveaux_ids | locaux and l["arrivee_id"] in anciens_ids | locaux) or
        (l["arrivee_id"] in nouveaux_ids | locaux and l["depart_id"] in anciens_ids | locaux)]
    meme = bool(actuelle and actuelle.version_id == version_id)
    return {"version": version, "adoption_id": actuelle.pk if actuelle else None,
            "garde": garde_adoption(classe, version_id, choix),
            "mise_a_jour": apercu_mise_a_jour(classe, actuelle, version),
            "revisions": choix.revisions, "communes": len(anciens_ids & nouveaux_ids),
            "nouvelles": nombre - len(anciens_ids & nouveaux_ids),
            "correspondances": liens, "ajouts": len(locaux), "hors_base": len(anciens_ids - nouveaux_ids), "meme": meme}


@transaction.atomic
def adopter_base(*, utilisateur, classe, version_id, revisions_attendues, adoption_attendue, adaptations_attendues=None, garde_attendue=None):
    classe_fournie = classe
    # Même ordre de coordination que les choix d'école.
    _application_verrouillee(classe.annee_scolaire)
    Ecole.objects.select_for_update().get(pk=classe.ecole_id)
    classe = Classe.objects.select_for_update().select_related("ecole").get(pk=classe.pk)
    apercu = apercu_adoption(utilisateur=utilisateur, classe=classe, version_id=version_id)
    if apercu["revisions"] != tuple(revisions_attendues) or apercu["adoption_id"] != adoption_attendue:
        raise ValidationError("Les choix ont changé. Consultez à nouveau l'aperçu avant de confirmer.")
    mise_a_jour = apercu["mise_a_jour"]
    if adaptations_attendues is not None and (not mise_a_jour or
            mise_a_jour["empreinte_adaptations"] != adaptations_attendues):
        raise ValidationError("Les adaptations ont changé. Consultez à nouveau les conséquences avant de confirmer.")
    if apercu["meme"]:
        return AdoptionReferentiel.objects.get(pk=apercu["adoption_id"])
    garde = apercu["garde"]
    if garde_attendue is None or garde["empreinte"] != list(garde_attendue):
        raise ValidationError("La situation de la classe ou les permissions ont changé. Préparez un nouvel aperçu.")
    if not garde["permis"]:
        raise ValidationError("Le changement après saisies est interdit. Une autorisation explicite de l'application, de l'école et de la classe est nécessaire.")
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
    if garde["niveau"] == "rouge":
        consommer_permission(utilisateur, classe)
    classe_fournie._adoption_referentiel_lecture = adoption
    return adoption
