"""Moteur central d'autorisation.

La session choisit un contexte d'école mais ne confère jamais un droit. Toute
opération inconnue est refusée.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from comptes.models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole

from .models import Classe, Ecole

ACCEDER_APPLICATION = "acceder_application"
ADMINISTRER_ECOLE = "administrer_ecole"
VOIR_CLASSES = "voir_classes"
VOIR_CLASSE = "voir_classe"
VOIR_LISTE_ELEVES = "voir_liste_eleves"
GERER_CLASSE = "gerer_classe"
GERER_ELEVES_CLASSE = "gerer_eleves_classe"
VOIR_AFFECTATIONS_ECOLE = "voir_affectations_ecole"
VOIR_AFFECTATIONS_CLASSE = "voir_affectations_classe"
GERER_AFFECTATIONS = "gerer_affectations"
VOIR_SUIVI = "voir_suivi"
MODIFIER_ETAT = "modifier_etat"
CONTRIBUER = "contribuer"
PREVISUALISER_CARNET = "previsualiser_carnet"
GENERER_CARNET = "generer_carnet"
VOIR_MEDIA = "voir_media"
TELECHARGER_MEDIA_ORIGINAL = "telecharger_media_original"


def _utilisateur_actif(utilisateur):
    return bool(
        utilisateur
        and getattr(utilisateur, "is_authenticated", False)
        and utilisateur.is_active
    )


def _periode_active(prefixe, date):
    return Q(
        **{f"{prefixe}etat": "active", f"{prefixe}date_debut__lte": date}
    ) & (
        Q(**{f"{prefixe}date_fin__isnull": True})
        | Q(**{f"{prefixe}date_fin__gte": date})
    )


def appartenances_actives(utilisateur, ecole=None, date=None):
    date = date or timezone.localdate()
    if not _utilisateur_actif(utilisateur):
        return AppartenanceEcole.objects.none()
    resultat = AppartenanceEcole.objects.filter(
        _periode_active("", date),
        utilisateur=utilisateur,
        ecole__etat=Ecole.ACTIVE,
    ).select_related("ecole", "utilisateur")
    if ecole is not None:
        resultat = resultat.filter(ecole=ecole)
    return resultat.distinct()


def appartenance_active(utilisateur, ecole, date=None):
    return appartenances_actives(utilisateur, ecole, date).first()


def responsabilites_direction_actives(utilisateur, ecole=None, date=None):
    date = date or timezone.localdate()
    return ResponsabiliteEcole.objects.filter(
        _periode_active("", date),
        appartenance__in=appartenances_actives(utilisateur, ecole, date),
        type=ResponsabiliteEcole.DIRECTION,
    ).select_related("appartenance", "appartenance__ecole")


def est_direction(utilisateur, ecole, date=None):
    return responsabilites_direction_actives(utilisateur, ecole, date).exists()


def affectations_actives(
    utilisateur,
    *,
    ecole=None,
    classe=None,
    types=None,
    date=None,
    exiger_classe_active=True,
):
    date = date or timezone.localdate()
    resultat = AffectationClasse.objects.filter(
        _periode_active("", date),
        appartenance__in=appartenances_actives(utilisateur, ecole, date),
    ).select_related("appartenance", "appartenance__ecole", "classe")
    if classe is not None:
        resultat = resultat.filter(classe=classe)
    if types is not None:
        resultat = resultat.filter(type__in=types)
    if exiger_classe_active:
        resultat = resultat.filter(classe__etat=Classe.ACTIVE)
    return resultat.distinct()


def affectation_active(utilisateur, classe, types=None, date=None):
    return affectations_actives(
        utilisateur, classe=classe, types=types, date=date
    ).first()


def peut_voir_suivi(utilisateur, classe, date=None):
    return affectation_active(
        utilisateur,
        classe,
        [AffectationClasse.RESPONSABLE, AffectationClasse.ENSEIGNANT_ASSOCIE],
        date,
    ) is not None


def peut_modifier_etat(utilisateur, classe, date=None):
    return affectation_active(
        utilisateur, classe, [AffectationClasse.RESPONSABLE], date
    ) is not None


def peut_contribuer(utilisateur, classe, date=None):
    return affectation_active(
        utilisateur,
        classe,
        [
            AffectationClasse.RESPONSABLE,
            AffectationClasse.ENSEIGNANT_ASSOCIE,
            AffectationClasse.CONTRIBUTEUR,
        ],
        date,
    ) is not None


def peut_voir_media(utilisateur, trace, date=None):
    from .models import AccesParcoursEleve

    if trace.supprime_le is not None or not trace.photo:
        return False
    eleve = trace.observation.eleve
    scolarite_courante = eleve.scolarite_courante()
    if scolarite_courante is None:
        return False
    if trace.scolarite_id == scolarite_courante.pk:
        return peut_voir_suivi(utilisateur, scolarite_courante.classe, date) or (
            trace.auteur_id == utilisateur.pk
            and peut_contribuer(utilisateur, scolarite_courante.classe, date)
        )
    return bool(
        trace.visible_carnet
        and peut_voir_suivi(utilisateur, scolarite_courante.classe, date)
        and AccesParcoursEleve.objects.filter(
            eleve=eleve, classe=scolarite_courante.classe
        ).exists()
    )


def peut_telecharger_media_original(utilisateur, trace, date=None):
    if not peut_voir_media(utilisateur, trace, date):
        return False
    classe_courante = trace.observation.eleve.classe
    return peut_modifier_etat(utilisateur, classe_courante, date) or (
        trace.auteur_id == utilisateur.pk
        and trace.scolarite_id == trace.observation.eleve.scolarite_courante().pk
        and peut_contribuer(utilisateur, classe_courante, date)
    )


def _ecole_ressource(ressource):
    if isinstance(ressource, Ecole):
        return ressource
    if isinstance(ressource, Classe):
        return ressource.ecole
    for attribut in ("ecole", "classe", "scolarite", "eleve", "observation", "domaine"):
        if not hasattr(ressource, attribut):
            continue
        parent = getattr(ressource, attribut)
        if attribut == "ecole":
            return parent
        trouvee = _ecole_ressource(parent)
        if trouvee:
            return trouvee
    return None


def _classe_ressource(ressource):
    if isinstance(ressource, Classe):
        return ressource
    if hasattr(ressource, "classe"):
        return ressource.classe
    if hasattr(ressource, "scolarite"):
        return ressource.scolarite.classe
    if hasattr(ressource, "observation"):
        return _classe_ressource(ressource.observation)
    if hasattr(ressource, "eleve"):
        scolarite = ressource.eleve.scolarite_courante()
        return scolarite.classe if scolarite else None
    if hasattr(ressource, "scolarite_courante"):
        scolarite = ressource.scolarite_courante()
        return scolarite.classe if scolarite else None
    return None


def autorise(utilisateur, operation, ressource=None, *, ecole=None, date=None):
    date = date or timezone.localdate()
    ecole_ressource = _ecole_ressource(ressource) if ressource is not None else None
    if ecole and ecole_ressource and ecole.pk != ecole_ressource.pk:
        return False
    ecole = ecole_ressource or ecole
    if ecole is None or not appartenance_active(utilisateur, ecole, date):
        return False
    direction = est_direction(utilisateur, ecole, date)
    classe = _classe_ressource(ressource) if ressource is not None else None
    if operation == ACCEDER_APPLICATION:
        return direction or affectations_actives(
            utilisateur, ecole=ecole, date=date
        ).exists()
    if operation in {
        ADMINISTRER_ECOLE,
        GERER_CLASSE,
        VOIR_AFFECTATIONS_ECOLE,
        GERER_AFFECTATIONS,
    }:
        return direction
    if operation == VOIR_CLASSES:
        return direction or affectations_actives(
            utilisateur, ecole=ecole, date=date, exiger_classe_active=False
        ).exists()
    if classe is None:
        return False
    if operation in {VOIR_CLASSE, VOIR_LISTE_ELEVES, VOIR_AFFECTATIONS_CLASSE}:
        return direction or affectation_active(utilisateur, classe, date=date) is not None
    if operation in {VOIR_SUIVI, PREVISUALISER_CARNET}:
        return peut_voir_suivi(utilisateur, classe, date)
    if operation in {MODIFIER_ETAT, GENERER_CARNET}:
        return peut_modifier_etat(utilisateur, classe, date)
    if operation == GERER_ELEVES_CLASSE:
        return direction or peut_modifier_etat(utilisateur, classe, date)
    if operation == CONTRIBUER:
        return peut_contribuer(utilisateur, classe, date)
    if operation == VOIR_MEDIA:
        return peut_voir_media(utilisateur, ressource, date)
    if operation == TELECHARGER_MEDIA_ORIGINAL:
        return peut_telecharger_media_original(utilisateur, ressource, date)
    return False


def ecoles_accessibles(utilisateur, operation=ACCEDER_APPLICATION, date=None):
    ids = [
        relation.ecole_id
        for relation in appartenances_actives(utilisateur, date=date)
        if autorise(utilisateur, operation, ecole=relation.ecole, date=date)
    ]
    return Ecole.objects.filter(pk__in=ids).order_by("nom", "pk")


def classes_accessibles(utilisateur, operation=VOIR_CLASSE, ecole=None, date=None):
    date = date or timezone.localdate()
    base = Classe.objects.filter(
        ecole__in=ecoles_accessibles(utilisateur, VOIR_CLASSES, date)
    )
    if ecole is not None:
        base = base.filter(ecole=ecole)
    if operation in {GERER_CLASSE, VOIR_AFFECTATIONS_ECOLE, GERER_AFFECTATIONS}:
        directions = responsabilites_direction_actives(utilisateur, date=date)
        return base.filter(
            ecole_id__in=directions.values("appartenance__ecole_id")
        )
    types = {
        VOIR_SUIVI: [AffectationClasse.RESPONSABLE, AffectationClasse.ENSEIGNANT_ASSOCIE],
        PREVISUALISER_CARNET: [AffectationClasse.RESPONSABLE, AffectationClasse.ENSEIGNANT_ASSOCIE],
        MODIFIER_ETAT: [AffectationClasse.RESPONSABLE],
        GENERER_CARNET: [AffectationClasse.RESPONSABLE],
        CONTRIBUER: list(dict(AffectationClasse.TYPES)),
        GERER_ELEVES_CLASSE: [AffectationClasse.RESPONSABLE],
    }.get(operation)
    affectations = affectations_actives(
        utilisateur,
        types=types,
        date=date,
        exiger_classe_active=operation
        not in {
            VOIR_CLASSE,
            VOIR_LISTE_ELEVES,
            VOIR_AFFECTATIONS_CLASSE,
        },
    )
    condition = Q(pk__in=affectations.values("classe_id"))
    if operation in {
        VOIR_CLASSE,
        VOIR_LISTE_ELEVES,
        VOIR_AFFECTATIONS_CLASSE,
        GERER_ELEVES_CLASSE,
    }:
        directions = responsabilites_direction_actives(utilisateur, date=date)
        condition |= Q(ecole_id__in=directions.values("appartenance__ecole_id"))
    return base.filter(condition).distinct()


def charger_classe_autorisee(utilisateur, pk, operation=VOIR_CLASSE, *, ecole=None, date=None):
    return get_object_or_404(
        classes_accessibles(utilisateur, operation, ecole, date), pk=pk
    )


def charger_ressource_autorisee(queryset, utilisateur, operation, *, ecole=None, date=None, **lookup):
    ressource = get_object_or_404(queryset, **lookup)
    if not autorise(utilisateur, operation, ressource, ecole=ecole, date=date):
        raise Http404
    return ressource


def charger_eleve_autorise(
    utilisateur, pk, operation=VOIR_SUIVI, *, ecole=None, date=None, actifs_seulement=False
):
    from .models import Eleve

    candidats = Eleve.objects.all()
    if ecole is not None:
        candidats = candidats.filter(ecole=ecole)
    if actifs_seulement:
        candidats = candidats.filter(archive_le__isnull=True)
    eleve = get_object_or_404(candidats, pk=pk)
    classe = _classe_ressource(eleve)
    if classe is None or not autorise(
        utilisateur, operation, classe, ecole=ecole, date=date
    ):
        raise Http404
    return eleve


def exiger(utilisateur, operation, ressource=None, *, ecole=None, date=None):
    if not autorise(utilisateur, operation, ressource, ecole=ecole, date=date):
        raise PermissionDenied


def toutes_autorisees(utilisateur, operation, ressources, *, ecole=None, date=None):
    return all(
        autorise(utilisateur, operation, objet, ecole=ecole, date=date)
        for objet in ressources
    )


def peut_auto_attribuer_temporairement(utilisateur, classe, motif, date_fin, date=None):
    date = date or timezone.localdate()
    return bool(
        est_direction(utilisateur, classe.ecole, date)
        and motif.strip()
        and date_fin
        and date_fin >= date
    )


def peut_activer_classe(utilisateur, classe, date=None):
    return bool(
        classe.etat == Classe.PREPARATION
        and est_direction(utilisateur, classe.ecole, date)
        and classe.responsables_actifs(date).exists()
    )


def peut_terminer_affectation(utilisateur, affectation, remplacement=None, date=None):
    date = date or timezone.localdate()
    if not est_direction(utilisateur, affectation.classe.ecole, date):
        return False
    if affectation.type != AffectationClasse.RESPONSABLE or affectation.classe.etat != Classe.ACTIVE:
        return True
    if affectation.classe.responsables_actifs(date).exclude(pk=affectation.pk).exists():
        return True
    return bool(
        remplacement
        and remplacement.classe_id == affectation.classe_id
        and remplacement.type == AffectationClasse.RESPONSABLE
        and remplacement.est_active(date)
    )


def peut_suspendre_urgence(utilisateur, affectation, date=None):
    return est_direction(utilisateur, affectation.classe.ecole, date)
