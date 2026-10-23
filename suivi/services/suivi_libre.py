"""Orchestration métier du suivi libre autour des services éprouvés."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from suivi.models import DisponibiliteCompetenceLocale, EleveApprentissage, Observation
from suivi.audit import journaliser
from suivi.services.ajouts_referentiels import creer_ajout, _verrouiller
from suivi.services.traces_communes import _scolarites, enregistrer_commune
from suivi.services.pedagogie import modifier_etat


@transaction.atomic
def associer(*, utilisateur, classe, locale, ids, adoption_attendue, retirer=False):
    from suivi.autorisations import MODIFIER_ETAT, autorise
    if not autorise(utilisateur, MODIFIER_ETAT, classe):
        raise PermissionDenied
    _verrouiller(utilisateur, classe.ecole, classe.annee_scolaire, classe, adoption_attendue)
    if not locale.suivi_libre or locale.ecole_id != classe.ecole_id:
        raise PermissionDenied
    # La reprise hors de la classe d'origine exige un accès pédagogique à un
    # usage antérieur, jamais le seul accès au catalogue de l'école.
    from suivi.suivi_libre import peut_reprendre
    if not peut_reprendre(utilisateur, classe, locale):
        raise PermissionDenied
    selection = _scolarites(classe, ids)
    if retirer:
        d = DisponibiliteCompetenceLocale.objects.filter(locale=locale, classe=classe).first()
        if d is None:
            raise ValidationError("Cette compétence n’est pas proposée dans cette classe.")
    else:
        d, _ = DisponibiliteCompetenceLocale.objects.get_or_create(locale=locale, classe=classe,
            defaults={"annee_scolaire": classe.annee_scolaire, "auteur": utilisateur})
    for sc in selection:
        if retirer:
            lien = EleveApprentissage.objects.filter(disponibilite=d, scolarite=sc).first()
            if lien is None:
                raise ValidationError("Cette compétence n’est pas proposée à un des élèves sélectionnés.")
        else:
            lien, _ = EleveApprentissage.objects.get_or_create(disponibilite=d, scolarite=sc)
        lien.active = not retirer
        lien.full_clean()
        lien.save()
    journaliser(utilisateur, "suivi_libre.portee_modifiee", d,
        nouvelles={"eleves": sorted(sc.eleve_id for sc in selection), "active": not retirer})
    return d


@transaction.atomic
def ajouter_reussite(*, utilisateur, classe, ids, domaine_id, libelle, niveau,
                     date_observation, adoption_attendue, sous_domaine_id=None,
                     commentaire="", photo=None, reussite=True, icone=""):
    selection = _scolarites(classe, ids)
    from suivi.models import bornes_annee_scolaire
    debut, fin = bornes_annee_scolaire(classe.annee_scolaire)
    if (reussite or commentaire or photo) and (not date_observation or not debut <= date_observation <= fin):
        raise ValidationError("La date doit appartenir à l’année scolaire de la classe.")
    locale = creer_ajout(utilisateur=utilisateur, ecole=classe.ecole,
        annee=classe.annee_scolaire, classe=classe, adoption_attendue=adoption_attendue,
        domaine_id=domaine_id, sous_domaine_id=sous_domaine_id, libelle=libelle,
        niveau=niveau, suivi_libre=True)
    associer(utilisateur=utilisateur, classe=classe, locale=locale, ids=ids,
             adoption_attendue=adoption_attendue)
    if icone:
        from suivi.models import ReglagePresentation
        from .presentation import enregistrer_reglage
        enregistrer_reglage(utilisateur, ReglagePresentation(ecole=classe.ecole,
            classe=classe, competence=locale.competence, mode=ReglagePresentation.REMPLACER, icone=icone))
    if not reussite and not (commentaire or photo):
        return locale
    valeurs = {"date_observation": date_observation, "commentaire": commentaire,
               "photo": photo, "reussite": reussite}
    if len(selection) == 1:
        from .pedagogie import enregistrer_trace
        enregistrer_trace(utilisateur=utilisateur, eleve=selection[0].eleve,
            competence=locale.competence, scolarite=selection[0], valeurs=valeurs)
    else:
        enregistrer_commune(utilisateur=utilisateur, classe=classe,
            competence=locale.competence, ids=ids, valeurs=valeurs)
    for sc in selection if reussite else []:
        modifier_etat(utilisateur=utilisateur, eleve=sc.eleve, competence=locale.competence,
                      statut=Observation.REUSSI, date_observation=date_observation)
    return locale
