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
    elif version.contenu.get("origine") != "source_declaree":
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
    avant, apres = anciens_ids | locaux, nouveaux_ids | locaux
    liens = []
    for lien in correspondances_classe(classe):
        depart, arrivee = lien["depart_id"], lien["arrivee_id"]
        if (depart in apres and arrivee in avant) or (arrivee in apres and depart in avant):
            liens.append({**lien,
                "succession": lien["type_lien"] == "remplace" and depart in apres - avant and arrivee in avant - apres})
    meme = bool(actuelle and actuelle.version_id == version_id)
    mise_a_jour = apercu_mise_a_jour(classe, actuelle, version)
    return {"version": version, "adoption_id": actuelle.pk if actuelle else None,
            "garde": garde_adoption(classe, version_id, choix,
                                    continue_suivi=bool(mise_a_jour and mise_a_jour["continue_suivi"])),
            "mise_a_jour": mise_a_jour,
            "revisions": choix.revisions, "communes": len(anciens_ids & nouveaux_ids),
            "nouvelles": nombre - len(anciens_ids & nouveaux_ids),
            "correspondances": liens, "ajouts": len(locaux), "hors_base": len(anciens_ids - nouveaux_ids), "meme": meme}


@transaction.atomic
def adopter_base(*, utilisateur, classe, version_id, revisions_attendues, adoption_attendue, adaptations_attendues=None, garde_attendue=None, initialisee_depuis_ecole=False, selection_manuelle=False, libelles_a_reprendre=(), phrases_a_reprendre=(), illustrations_a_reprendre=()):
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
    libelles_a_reprendre = set(libelles_a_reprendre)
    reprenables = mise_a_jour["libelles_reprenables"] if mise_a_jour else {}
    if libelles_a_reprendre and (adaptations_attendues is None or
                                not libelles_a_reprendre <= reprenables.keys()):
        raise ValidationError("Les libellés sélectionnés ne correspondent pas à l’aperçu.")
    phrases_a_reprendre = set(phrases_a_reprendre)
    phrases = mise_a_jour["phrases_reprenables"] if mise_a_jour else {}
    if phrases_a_reprendre:
        from .presentation import verifier_droit
        if adaptations_attendues is None or not phrases_a_reprendre <= phrases.keys():
            raise ValidationError("Les phrases sélectionnées ne correspondent pas à l’aperçu.")
        verifier_droit(utilisateur, classe.ecole, classe)
    illustrations_a_reprendre = set(illustrations_a_reprendre)
    illustrations = mise_a_jour["illustrations_reprenables"] if mise_a_jour else {}
    if illustrations_a_reprendre and (adaptations_attendues is None or
                                      not illustrations_a_reprendre <= illustrations.keys()):
        raise ValidationError("Les illustrations sélectionnées ne correspondent pas à l’aperçu.")
    if initialisee_depuis_ecole:
        choix = choix_bases(classe.ecole, classe.annee_scolaire)
        if (AdoptionReferentiel.objects.filter(classe=classe).exists() or
                not choix.proposee or choix.proposee.pk != version_id or apercu["garde"]["saisies"]):
            raise ValidationError("L'initialisation depuis l'école est réservée à une classe neuve sans saisie.")
    if apercu["meme"]:
        return AdoptionReferentiel.objects.get(pk=apercu["adoption_id"])
    garde = apercu["garde"]
    if garde_attendue is None or garde["empreinte"] != list(garde_attendue):
        raise ValidationError("La situation de la classe ou les permissions ont changé. Préparez un nouvel aperçu.")
    if not garde["permis"]:
        raise ValidationError("Le changement après saisies est interdit. Une autorisation explicite de l'application, de l'école et de la classe est nécessaire.")
    version = apercu["version"]
    if adoption_attendue is not None:
        selection_manuelle = AdoptionReferentiel.objects.get(pk=adoption_attendue).selection_manuelle
    if libelles_a_reprendre:
        from .adaptations_referentiels import enregistrer_adaptation
        from suivi.models import Competence
        competences = Competence.objects.in_bulk(libelles_a_reprendre)
        for identifiant in sorted(libelles_a_reprendre):
            choix = reprenables[identifiant]
            enregistrer_adaptation(utilisateur=utilisateur, ecole=classe.ecole,
                annee=classe.annee_scolaire, classe=classe,
                competence=competences[choix["id"]], libelle=None, visible=choix["visible"],
                revision_attendue=choix["revision"], adoption_attendue=adoption_attendue)
    if phrases_a_reprendre:
        from .presentation import enregistrer_formulation
        from suivi.models import Competence, ReglagePresentation
        selections = [phrases[cle] for cle in sorted(phrases_a_reprendre)]
        competences = Competence.objects.in_bulk({c["competence_id"] for c in selections})
        for choix in selections:
            enregistrer_formulation(utilisateur=utilisateur, competence=competences[choix["competence_id"]],
                                    classe=classe, cle=f"base-{choix['id']}", mode=ReglagePresentation.HERITER)
    if illustrations_a_reprendre:
        from suivi.models import ReglagePresentation
        from .presentation import enregistrer_reglage

        for identifiant in sorted(illustrations_a_reprendre):
            reglage = illustrations[identifiant]
            reglage.mode = ReglagePresentation.HERITER
            enregistrer_reglage(utilisateur, reglage)
    contenu = definir_version_ecole(classe.ecole, version)
    annuel, _ = ReferentielAnnuel.objects.get_or_create(ecole=classe.ecole, annee_scolaire=classe.annee_scolaire,
                                                      defaults={"version_proposee": version})
    AdoptionReferentiel.objects.filter(classe=classe, courante=True).update(courante=False)
    adoption = AdoptionReferentiel(classe=classe, annuel=annuel, version=version, contenu=contenu,
                                   auteur=utilisateur, adopte_le=timezone.now(),
                                   initialisee_depuis_ecole=initialisee_depuis_ecole, selection_manuelle=selection_manuelle)
    adoption.full_clean()
    adoption.save()
    for c in contenu["competences"]:
        usage = UsageCompetence(adoption=adoption, competence_id=c["id"], cle_definition=c.get("cle_definition", f"locale-{c['id']}"))
        usage.full_clean()
        usage.save()
    journaliser(utilisateur, "referentiel.base_classe", adoption,
        anciennes={"adoption": apercu["adoption_id"]}, nouvelles={"version": version.pk, "initialisee_depuis_ecole": initialisee_depuis_ecole,
                    "selection_manuelle": selection_manuelle})
    if garde["niveau"] != "info" and garde["permission"]["classe"]:
        consommer_permission(utilisateur, classe)
    classe_fournie._adoption_referentiel_lecture = adoption
    return adoption
