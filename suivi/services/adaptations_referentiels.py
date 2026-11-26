"""Adaptations fidèles et réversibles, propres à une école ou classe annuelle."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.audit import instantane, journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import AdaptationCompetence, AdoptionReferentiel, Classe, Competence, Ecole
from suivi.adaptations_referentiels import contenu_avec_emprunts, contenus_ecole
from suivi.referentiels import contenu_adoption, contenu_origine
from suivi.rubriques import contenu_classement
from .choix_bases_referentiels import verifier_annee


@transaction.atomic
def enregistrer_adaptation(*, utilisateur, ecole, annee, competence, libelle, visible,
                           revision_attendue, classe=None, adoption_attendue=None, destination=None, depuis_catalogue=False):
    verifier_annee(annee)
    from suivi.suivi_libre import est_libre
    from suivi.autorisations import MODIFIER_ETAT
    if est_libre(competence) and (not classe or not autorise(utilisateur, MODIFIER_ETAT, classe)):
        raise PermissionDenied
    if competence.domaine.ecole_id != ecole.pk:
        raise PermissionDenied
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                   classe if classe else ecole):
        raise PermissionDenied
    if type(revision_attendue) is not int or revision_attendue < 0:
        raise ValidationError("Consultez à nouveau les choix avant d'enregistrer.")
    if visible is not None and type(visible) is not bool:
        raise ValidationError("Choisissez de garder, montrer ou masquer la compétence.")
    if libelle is not None:
        if not isinstance(libelle, str) or not libelle.strip() or len(libelle.strip()) > 300:
            raise ValidationError("Précisez un libellé de 1 à 300 caractères.")
        libelle = libelle.strip()
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if classe:
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee:
            raise PermissionDenied
        adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).select_related("version").first()
        if not adoption or adoption.clos:
            raise ValidationError("Choisissez une base pour une classe ouverte avant de l'adapter.")
        if adoption.pk != adoption_attendue:
            raise ValidationError("La base de la classe a changé. Consultez à nouveau les compétences.")
        if depuis_catalogue and not any(c["id"] == competence.pk for c in contenu_adoption(adoption)["competences"]):
            raise ValidationError("Cette compétence ne figure plus dans le catalogue de la classe.")
        contenus = [contenu_avec_emprunts(contenu_origine(adoption), classe)]
        # Une compétence sortie de la base reste adaptable pour le parcours,
        # mais la montrer ne l'ajoute jamais à la base des prochaines saisies.
        contenus += [contenu_origine(a) for a in AdoptionReferentiel.objects.filter(
            classe=classe).exclude(pk=adoption.pk).select_related("version")]
    else:
        contenus = [contenu for _, contenu in contenus_ecole(ecole, annee)]
    from suivi.models import DisponibiliteCompetenceLocale
    locaux = DisponibiliteCompetenceLocale.objects.filter(locale__ecole=ecole,
        locale__competence=competence, annee_scolaire=annee)
    if classe:
        locaux = locaux.filter(classe=classe)
    if not locaux.exists() and not any(c["id"] == competence.pk for contenu in contenus for c in contenu.get("competences", [])):
        raise ValidationError("Cette compétence ne figure pas dans les bases de ce périmètre.")
    regle, _ = AdaptationCompetence.objects.get_or_create(ecole=ecole, annee_scolaire=annee,
                                                        classe=classe, competence=competence)
    if regle.revision != revision_attendue:
        raise ValidationError("Ces choix ont changé. Consultez-les à nouveau avant d'enregistrer.")
    champs = ("libelle", "visible", "domaine_destination_id", "sous_domaine_destination_id", "revision")
    anciennes = instantane(regle, champs)
    if destination is not None:
        if not classe or not depuis_catalogue:
            raise PermissionDenied
        domaine, sous_domaine = destination
        classement = contenu_classement(adoption)
        if not any(d["id"] == domaine for d in classement["domaines"]) or (
                sous_domaine is not None and not any(s["id"] == sous_domaine and s["domaine_id"] == domaine
                                                      for s in classement["sous_domaines"])):
            raise ValidationError("La rubrique de destination n’est plus disponible.")
        regle.domaine_destination_id, regle.sous_domaine_destination_id = destination
    if classe:
        from .heritage_sources import consigner_heritage, relever_heritage

        contexte_heritage = {"classe_origine": classe, "competence_id": competence.pk}
        historique_avant = relever_heritage(**contexte_heritage)
    regle.libelle, regle.visible = libelle, visible
    regle.revision += 1
    regle.full_clean()
    regle.save()
    journaliser(utilisateur, "referentiel.competence_adaptee", regle, anciennes=anciennes,
                nouvelles=instantane(regle, champs))
    if classe and historique_avant:
        consigner_heritage(historique_avant, relever_heritage(**contexte_heritage), nom_source=classe.nom)
    return regle


@transaction.atomic
def ajouter_au_suivi(*, utilisateur, classe, competence_id, adoption_attendue, revision_attendue):
    """Activer une compétence du catalogue adopté, sans saisir d'observation."""
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    Ecole.objects.select_for_update().get(pk=classe.ecole_id)
    classe = Classe.objects.select_for_update().get(pk=classe.pk)
    adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).select_related("version").first()
    if not adoption or adoption.clos or adoption.pk != adoption_attendue:
        raise ValidationError("Le catalogue de la classe a changé. Rechargez la page.")
    if not any(c["id"] == competence_id for c in contenu_origine(adoption).get("competences", [])):
        raise ValidationError("Cette compétence ne fait pas partie du catalogue adopté.")
    competence = Competence.objects.filter(pk=competence_id, domaine__ecole=classe.ecole).first()
    if competence is None:
        raise ValidationError("Cette compétence est indisponible.")
    regle = AdaptationCompetence.objects.filter(classe=classe, competence=competence,
                                               annee_scolaire=classe.annee_scolaire).first()
    if regle and regle.visible is True and regle.revision == revision_attendue:
        return
    enregistrer_adaptation(utilisateur=utilisateur, ecole=classe.ecole,
        annee=classe.annee_scolaire, competence=competence, libelle=regle.libelle if regle else None,
        visible=True, revision_attendue=revision_attendue, classe=classe, adoption_attendue=adoption.pk)
