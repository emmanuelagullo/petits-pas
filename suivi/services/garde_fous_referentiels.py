"""Restrictions annuelles et classement partagé des changements de base."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import (AdoptionReferentiel, ChoixApplicationAnnuel, ChoixEcoleAnnuel,
                         Classe, Ecole, EtatAnnuelObservation, Observation,
                         PermissionChangementClasse, Trace, TraceCommune)
from .choix_bases_referentiels import _application_verrouillee, verifier_annee


def permissions(ecole, annee, classe=None):
    application = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    locale = ChoixEcoleAnnuel.objects.filter(ecole=ecole, annee_scolaire=annee).first()
    propre = PermissionChangementClasse.objects.filter(classe=classe).first() if classe else None
    valeurs = [bool(application and application.changements_apres_saisies),
               bool(locale and locale.changements_apres_saisies), bool(propre and propre.ouverte)]
    revisions = [application.revision if application else 0, locale.revision if locale else 0,
                 propre.revision if propre else 0]
    blocage = next((nom for nom, valeur in zip(("application", "école", "classe"), valeurs) if not valeur), None)
    return {"application": valeurs[0], "ecole": valeurs[1], "classe": valeurs[2],
            "effective": all(valeurs), "blocage": blocage, "empreinte": valeurs + revisions}


def saisies_classe(classe):
    # Inclure les anciennes adoptions, les élèves déplacés et les suppressions logiques.
    annuels = EtatAnnuelObservation.objects.filter(connu=True).filter(
        Q(usage__adoption__classe=classe) |
        Q(annee_scolaire=classe.annee_scolaire, observation__eleve__scolarites__classe=classe))
    traces = Trace.objects.filter(Q(usage_referentiel__adoption__classe=classe) | Q(scolarite__classe=classe))
    communes = TraceCommune.objects.filter(Q(classe=classe) | Q(usage_referentiel__adoption__classe=classe))
    # Une observation sans état annuel connu n'est pas datée artificiellement.
    ambigu = Observation.objects.filter(eleve__scolarites__classe=classe).exclude(etats_annuels__connu=True).exists()
    return {"presentes": annuels.exists() or traces.exists() or communes.exists() or ambigu,
            "ambigu": ambigu}


def garde_adoption(classe, version_id, choix):
    actuelle = AdoptionReferentiel.objects.filter(classe=classe, courante=True).first()
    meme = bool(actuelle and actuelle.version_id == version_id)
    saisies = saisies_classe(classe)
    permission = permissions(classe.ecole, classe.annee_scolaire, classe)
    niveau = "info" if meme or (not actuelle and not saisies["presentes"] and
                               choix.proposee and choix.proposee.pk == version_id) else (
                               "rouge" if saisies["presentes"] else "orange")
    return {"niveau": niveau, "saisies": saisies["presentes"], "ambigu": saisies["ambigu"],
            "permission": permission, "permis": niveau != "rouge" or permission["effective"],
            "empreinte": [niveau, saisies["ambigu"], *permission["empreinte"]]}


@transaction.atomic
def regler_permission_application(*, annee, ouverte, revision_attendue, confirmer=False):
    verifier_annee(annee)
    if type(ouverte) is not bool or type(revision_attendue) is not int:
        raise ValidationError("Précisez la permission et la révision consultée.")
    if ouverte and not confirmer:
        raise ValidationError("Confirmez explicitement l'ouverture des changements après saisies.")
    regle = _application_verrouillee(annee)
    if regle.revision != revision_attendue:
        raise ValidationError("Les permissions ont changé. Consultez-les à nouveau.")
    if regle.changements_apres_saisies != ouverte:
        regle.historique_permissions = [*regle.historique_permissions, {
            "date": timezone.now().isoformat(), "avant": regle.changements_apres_saisies,
            "apres": ouverte, "origine": "commande_exploitation"}]
        regle.changements_apres_saisies = ouverte
        regle.revision += 1
        regle.save(update_fields=["changements_apres_saisies", "historique_permissions", "revision"])
    return regle


@transaction.atomic
def regler_permission(*, utilisateur, ecole, annee, ouverte, empreinte_attendue, classe=None):
    verifier_annee(annee)
    if type(ouverte) is not bool or (classe and (classe.ecole_id != ecole.pk or classe.annee_scolaire != annee)):
        raise ValidationError("La permission ne correspond pas à cette école et cette année.")
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                    classe or ecole):
        raise PermissionDenied
    _application_verrouillee(annee)
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if classe:
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if AdoptionReferentiel.objects.filter(classe=classe, courante=True, clos=True).exists():
            raise ValidationError("Les choix de cette classe sont clos.")
    etat = permissions(ecole, annee, classe)
    if etat["empreinte"] != list(empreinte_attendue):
        raise ValidationError("Les permissions ont changé. Consultez-les à nouveau.")
    if ouverte and (not etat["application"] or (classe and not etat["ecole"])):
        raise ValidationError("Le niveau supérieur interdit les changements après saisies.")
    if classe:
        regle, _ = PermissionChangementClasse.objects.get_or_create(classe=classe)
        champ = "ouverte"
    else:
        regle, _ = ChoixEcoleAnnuel.objects.get_or_create(ecole=ecole, annee_scolaire=annee)
        champ = "changements_apres_saisies"
    avant = getattr(regle, champ)
    if avant != ouverte:
        setattr(regle, champ, ouverte)
        regle.revision += 1
        regle.save(update_fields=[champ, "revision"])
        journaliser(utilisateur, "referentiel.permission", regle,
                    anciennes={"ouverte": avant}, nouvelles={"ouverte": ouverte, "annee": annee})
    return regle


def consommer_permission(utilisateur, classe):
    regle = PermissionChangementClasse.objects.get(classe=classe)
    regle.ouverte = False
    regle.revision += 1
    regle.save(update_fields=["ouverte", "revision"])
    journaliser(utilisateur, "referentiel.permission_consommee", regle,
                anciennes={"ouverte": True}, nouvelles={"ouverte": False})
