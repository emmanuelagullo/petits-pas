"""Conservation finale d'une classe ; service interne avant le parcours de clôture."""
from copy import deepcopy

from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction

from suivi.autorisations import ADMINISTRER_ECOLE, MODIFIER_ETAT, autorise
from suivi.audit import journaliser
from suivi.models import (AdoptionReferentiel, EtatAnnuelObservation, Observation,
                          RessourceReferentiel, UsageCompetence)
from suivi.presentation import illustration_effective, propositions


@transaction.atomic
def clore(*, utilisateur, classe):
    if not (autorise(utilisateur, MODIFIER_ETAT, classe) or autorise(utilisateur, ADMINISTRER_ECOLE, classe.ecole)):
        raise PermissionDenied
    adoption = AdoptionReferentiel.objects.select_for_update().get(classe=classe, courante=True)
    if adoption.clos:
        return adoption
    ressources = []

    def conserver(image):
        resultat = {"provenance": image.provenance, "icone": "", "photo": "", "ressource_id": None}
        if image.photo:
            ressource, _ = RessourceReferentiel.objects.get_or_create(annuel=adoption.annuel, fichier=image.photo)
        elif image.statique:
            chemin = finders.find(image.statique)
            if not chemin:
                raise ValidationError("Une illustration fournie est introuvable ; clôture annulée.")
            ressource = RessourceReferentiel(annuel=adoption.annuel)
            with open(chemin, "rb") as fichier:
                ressource.fichier.save(chemin.rsplit("/", 1)[-1], File(fichier), save=True)
        else:
            return resultat
        ressources.append(ressource.pk)
        resultat.update(photo=ressource.fichier.name, ressource_id=ressource.pk)
        return resultat

    final = {"contenu": deepcopy(adoption.version.contenu), "illustrations": {}, "propositions": {},
             "couverture": conserver(illustration_effective(classe.ecole, classe=classe))}
    usages = list(UsageCompetence.objects.filter(adoption=adoption).select_related("competence"))
    actifs = {u.competence_id: u.competence.active for u in usages}
    for definition in final["contenu"].get("competences", []):
        definition["active"] = definition["active"] and actifs.get(definition["id"], False)
    for usage in usages:
        competence = usage.competence
        final["illustrations"][str(competence.pk)] = conserver(illustration_effective(classe.ecole, competence, classe))
        final["propositions"][str(competence.pk)] = propositions(competence, classe, inclure_masquees=True)
        for observation in Observation.objects.filter(competence=competence, eleve__scolarites__classe=classe).distinct():
            # Photographier l'état connu aujourd'hui à la clôture ne reconstruit
            # pas le passé. Les états annuels déjà renseignés sont conservés.
            etat, _ = EtatAnnuelObservation.objects.get_or_create(
                observation=observation, annee_scolaire=classe.annee_scolaire)
            if not etat.connu:
                # Une ancienne année reprise ne gagne pas de réussite depuis le
                # suivi courant : seul un nouvel état saisi dans l'année est connu.
                etat.usage = usage
                if classe.statut_annee == "courante":
                    etat.connu = True
                    etat.statut = observation.statut
                    etat.date_observation = observation.date_observation
                etat.full_clean()
                etat.save()
    final["ressources"] = ressources
    adoption.etat_final = final
    adoption.clos = True
    adoption.save(update_fields=["etat_final", "clos"])
    classe._adoption_referentiel_lecture = adoption
    journaliser(utilisateur, "referentiel.classe_close", adoption, nouvelles={"classe": classe.pk})
    return adoption
