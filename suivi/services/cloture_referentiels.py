"""Conservation finale d'une classe ; service interne avant le parcours de clôture."""
from copy import deepcopy

from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction

from suivi.autorisations import ADMINISTRER_ECOLE, MODIFIER_ETAT, autorise
from suivi.audit import journaliser
from suivi.models import (AdoptionReferentiel, Classe, Ecole, EtatAnnuelObservation, Observation,
                          RessourceReferentiel, UsageCompetence)
from suivi.presentation import illustration_effective, propositions
from suivi.referentiels import arbre_competences, contenu_adoption


@transaction.atomic
def clore(*, utilisateur, classe):
    if not (autorise(utilisateur, MODIFIER_ETAT, classe) or autorise(utilisateur, ADMINISTRER_ECOLE, classe.ecole)):
        raise PermissionDenied
    Ecole.objects.select_for_update().get(pk=classe.ecole_id)
    Classe.objects.select_for_update().get(pk=classe.pk)
    adoption = AdoptionReferentiel.objects.select_for_update().get(classe=classe, courante=True)
    classe._adoption_referentiel_lecture = adoption
    if adoption.clos:
        return adoption
    ressources = []

    def conserver(image):
        resultat = {"provenance": image.provenance, "icone": "", "photo": "",
                    "ressource_id": None}
        if image.photo:
            ressource, _ = RessourceReferentiel.objects.get_or_create(
                annuel=adoption.annuel,
                fichier=image.photo,
            )
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
        resultat.update(
            photo=ressource.fichier.name,
            ressource_id=ressource.pk,
        )
        return resultat

    from suivi.correspondances_referentiels import correspondances_classe
    final = {"contenu": deepcopy(contenu_adoption(adoption)), "illustrations": {}, "propositions": {},
             "couverture": conserver(illustration_effective(classe.ecole, classe=classe)), "etats": [], "correspondances": correspondances_classe(classe)}
    observations = Observation.objects.filter(eleve__scolarites__classe=classe).distinct()
    suivies = set(observations.values_list("competence_id", flat=True))
    actuelles = {c["id"] for c in final["contenu"].get("competences", [])}
    arbre = arbre_competences(classe.ecole, classe=classe, inclure_ids=suivies | actuelles)
    competences = {c.pk: c for d in arbre for c in d.visibles}
    # Les anciennes définitions restent lisibles, sans revenir dans la saisie.
    for competence_id in sorted(suivies - actuelles):
        competence = competences.get(competence_id)
        if competence is None:
            raise ValidationError("Une compétence du parcours ne peut pas être retrouvée ; clôture annulée.")
        contenu = competence._contenu_referentiel
        for rubrique in ("domaines", "sous_domaines", "attendus", "formulations", "competences"):
            presentes = {ligne["id"] for ligne in final["contenu"].get(rubrique, [])}
            for ligne in contenu.get(rubrique, []):
                utile = (rubrique == "domaines" and ligne["id"] == competence.domaine_id
                    or rubrique == "sous_domaines" and ligne["id"] == competence.sous_domaine_id
                    or rubrique == "attendus" and ligne["domaine_id"] == competence.domaine_id
                    or rubrique == "formulations" and ligne["competence_id"] == competence_id
                    or rubrique == "competences" and ligne["id"] == competence_id)
                if not utile or ligne["id"] in presentes:
                    continue
                copie = deepcopy(ligne)
                if rubrique == "competences":
                    copie["active"] = False
                final["contenu"].setdefault(rubrique, []).append(copie)
                presentes.add(ligne["id"])
    usages = {u.competence_id: u for u in UsageCompetence.objects.filter(
        adoption__classe=classe).order_by("adoption_id", "pk")}
    for competence in competences.values():
        usage = usages.get(competence.pk)
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
                if not observation.eleve.scolarites.filter(annee_scolaire__gt=classe.annee_scolaire).exists():
                    etat.connu = True
                    etat.statut = observation.statut
                    etat.date_observation = observation.date_observation
                etat.full_clean()
                etat.save()
            final["etats"].append({"observation_id": etat.observation_id, "statut": etat.statut,
                "date_observation": etat.date_observation.isoformat() if etat.date_observation else None,
                "connu": etat.connu})
    final["ressources"] = ressources
    adoption.etat_final = final
    adoption.clos = True
    adoption.save(update_fields=["etat_final", "clos"])
    classe._adoption_referentiel_lecture = adoption
    journaliser(utilisateur, "referentiel.classe_close", adoption, nouvelles={"classe": classe.pk})
    return adoption
