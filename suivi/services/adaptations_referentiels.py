"""Adaptations fidèles et réversibles, propres à une école ou classe annuelle."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from suivi.audit import instantane, journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import AdaptationCompetence, AdoptionReferentiel, Classe, Ecole
from suivi.adaptations_referentiels import contenus_ecole
from suivi.referentiels import contenu_origine
from .choix_bases_referentiels import verifier_annee


@transaction.atomic
def enregistrer_adaptation(*, utilisateur, ecole, annee, competence, libelle, visible,
                           revision_attendue, meme_sens=False, classe=None, adoption_attendue=None):
    verifier_annee(annee)
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
        if meme_sens is not True:
            raise ValidationError("Confirmez que votre libellé garde le même apprentissage.")
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
        contenus = [contenu_origine(adoption)]
        # Une compétence sortie de la base reste adaptable pour le parcours,
        # mais la montrer ne l'ajoute jamais à la base des prochaines saisies.
        contenus += [contenu_origine(a) for a in AdoptionReferentiel.objects.filter(
            classe=classe).exclude(pk=adoption.pk).select_related("version")]
    else:
        contenus = [contenu for _, contenu in contenus_ecole(ecole, annee)]
    if not any(c["id"] == competence.pk for contenu in contenus for c in contenu.get("competences", [])):
        raise ValidationError("Cette compétence ne figure pas dans les bases de ce périmètre.")
    regle, _ = AdaptationCompetence.objects.get_or_create(ecole=ecole, annee_scolaire=annee,
                                                        classe=classe, competence=competence)
    if regle.revision != revision_attendue:
        raise ValidationError("Ces choix ont changé. Consultez-les à nouveau avant d'enregistrer.")
    anciennes = instantane(regle, ("libelle", "visible", "revision"))
    regle.libelle, regle.visible = libelle, visible
    regle.revision += 1
    regle.full_clean()
    regle.save()
    journaliser(utilisateur, "referentiel.competence_adaptee", regle, anciennes=anciennes,
                nouvelles=instantane(regle, ("libelle", "visible", "revision")))
    return regle
