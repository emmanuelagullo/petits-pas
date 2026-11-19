"""Activation et choix d’élèves sans attribution de réussite."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.audit import journaliser
from suivi.autorisations import MODIFIER_ETAT, autorise
from suivi.models import AdaptationCompetence, EleveCompetenceSelectionnee
from suivi.referentiels import contenu_adoption
from suivi.suivi_libre import est_libre
from .ajouts_referentiels import _verrouiller
from .traces_communes import _scolarites


@transaction.atomic
def regler_selection(*, utilisateur, classe, competence, adoption_attendue, revision_attendue, ids=None):
    if not autorise(utilisateur, MODIFIER_ETAT, classe):
        raise PermissionDenied
    adoption = _verrouiller(utilisateur, classe.ecole, classe.annee_scolaire, classe, adoption_attendue)
    if est_libre(competence) or not any(c["id"] == competence.pk for c in contenu_adoption(adoption)["competences"]):
        raise PermissionDenied
    selection = _scolarites(classe, ids) if ids is not None else []
    regle, _ = AdaptationCompetence.objects.get_or_create(classe=classe, competence=competence,
        defaults={"ecole": classe.ecole, "annee_scolaire": classe.annee_scolaire})
    if regle.revision != revision_attendue:
        raise ValidationError("Le suivi a changé. Rechargez le formulaire de sélection.")
    # En passant d’une compétence commune à un sous-groupe, conserver les
    # observations existantes et leur contexte de lecture.
    liens = regle.eleves_selectionnes.all()
    liens.filter(active=True).update(active=False)
    for scolarite in selection:
        EleveCompetenceSelectionnee.objects.update_or_create(
            adaptation=regle, scolarite=scolarite, defaults={"active": True})
    regle.selection_eleves = ids is not None
    regle.visible = True
    regle.revision += 1
    regle.full_clean()
    regle.save(update_fields=["selection_eleves", "visible", "revision"])
    journaliser(utilisateur, "referentiel.selection_eleves", regle,
                nouvelles={"toute_la_classe": ids is None, "eleves": sorted(s.eleve_id for s in selection)})
