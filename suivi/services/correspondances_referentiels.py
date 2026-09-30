"""Validation et retrait explicites des liens de l'école ou de la classe annuelle."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import (AdoptionReferentiel, Classe, CompetenceLocale, CorrespondanceCompetence, Ecole)
from suivi.adaptations_referentiels import contenus_ecole
from suivi.referentiels import contenu_origine
from .ajouts_referentiels import catalogue_reprises
from .choix_bases_referentiels import verifier_annee


def catalogue_liens(*, utilisateur, ecole, annee, classe=None):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                   classe if classe else ecole):
        raise PermissionDenied
    if classe and (classe.ecole_id != ecole.pk or classe.annee_scolaire != annee):
        raise PermissionDenied
    bases = {v.pk: (v, c) for v, c in contenus_ecole(ecole, annee)}
    # Définitions des bases déjà utilisées, sans données d'élève ni réglage
    # privé d'une autre classe. Les versions retirées restent des origines lisibles.
    for adoption in AdoptionReferentiel.objects.filter(classe__ecole=ecole,
            classe__annee_scolaire__lte=annee).select_related("version__source").order_by("-pk"):
        bases.setdefault(adoption.version_id, (adoption.version, contenu_origine(adoption)))
    resultat = {}
    for version, contenu in bases.values():
        for c in contenu.get("competences", []):
            reference = f"base:{version.pk}:{c['id']}"
            resultat[reference] = {"reference": reference, "competence_id": c["id"], "version_id": version.pk,
                "libelle": c["libelle"], "code": c["code"], "niveau": c["niveau"],
                "origine": f"{version.source.titre} ({version.source.identifiant}) — version {version.numero}", "locale_id": None}
    locales = catalogue_reprises(utilisateur=utilisateur, ecole=ecole, annee=annee, classe=classe) if classe else (
        CompetenceLocale.objects.filter(ecole=ecole, disponibilites__annee_scolaire__lte=annee).distinct())
    for locale in locales.select_related("classe_origine"):
        c = locale.definition["competences"][0]
        reference = f"ajout:{locale.pk}"
        resultat[reference] = {"reference": reference, "competence_id": locale.competence_id, "version_id": None,
            "libelle": c["libelle"], "code": c["code"], "niveau": c["niveau"], "locale_id": locale.pk,
            "origine": f"Ajout de {locale.classe_origine.libelle_avec_annee}" if locale.classe_origine else "Ajout de l'école"}
    return resultat


def _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                   classe if classe else ecole):
        raise PermissionDenied
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if classe:
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee:
            raise PermissionDenied
        adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).first()
        if not adoption or adoption.clos:
            raise ValidationError("Choisissez une base pour une classe ouverte avant de relier des compétences.")
        if adoption.pk != adoption_attendue:
            raise ValidationError("La base a changé. Consultez à nouveau les correspondances.")


def _sans_cycle(ecole, annee, classe, depart_id, arrivee_id):
    liens = CorrespondanceCompetence.objects.filter(ecole=ecole, annee_scolaire=annee, active=True, type_lien="remplace")
    # Une nouvelle règle d'école ne doit pas créer un cycle dans une classe
    # ouverte qui possède ses propres liens. Une classe close lit son instantané.
    classes = [classe.pk] if classe else [None] + list(Classe.objects.filter(ecole=ecole,
        annee_scolaire=annee).exclude(pk__in=AdoptionReferentiel.objects.filter(courante=True, clos=True).values("classe_id")).values_list("pk", flat=True))
    valeurs = list(liens.values_list("classe_id", "depart_id", "arrivee_id"))
    for classe_id in classes:
        graphe = {}
        for portee, depart, arrivee in valeurs:
            if portee is None or portee == classe_id:
                graphe.setdefault(depart, set()).add(arrivee)
        suivants, vus = [arrivee_id], set()
        while suivants:
            sommet = suivants.pop()
            if sommet == depart_id:
                raise ValidationError("Ces remplacements formeraient une boucle. Vérifiez le sens des liens.")
            if sommet not in vus:
                vus.add(sommet)
                suivants.extend(graphe.get(sommet, ()))


@transaction.atomic
def relier_competences(*, utilisateur, ecole, annee, reference_depart, reference_arrivee,
                       type_lien, justification, classe=None, adoption_attendue=None):
    _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    catalogue = catalogue_liens(utilisateur=utilisateur, ecole=ecole, annee=annee, classe=classe)
    depart, arrivee = catalogue.get(reference_depart), catalogue.get(reference_arrivee)
    if depart is None or arrivee is None:
        raise PermissionDenied
    if type_lien not in dict(CorrespondanceCompetence.TYPES):
        raise ValidationError("Choisissez un type de lien proposé.")
    if not isinstance(justification, str) or not justification.strip() or len(justification.strip()) > 1000:
        raise ValidationError("Expliquez ce lien en 1 à 1000 caractères.")
    if depart["competence_id"] == arrivee["competence_id"]:
        raise ValidationError("Il s'agit déjà de la même compétence ; aucun lien vers elle-même n'est créé.")
    if type_lien == "remplace":
        _sans_cycle(ecole, annee, classe, depart["competence_id"], arrivee["competence_id"])
    if CorrespondanceCompetence.objects.filter(ecole=ecole, annee_scolaire=annee, classe=classe,
        reference_depart=reference_depart, reference_arrivee=reference_arrivee, type_lien=type_lien, active=True).exists():
        raise ValidationError("Ce lien est déjà présent dans ce périmètre.")
    lien = CorrespondanceCompetence(ecole=ecole, annee_scolaire=annee, classe=classe,
        depart_id=depart["competence_id"], arrivee_id=arrivee["competence_id"],
        version_depart_id=depart["version_id"], version_arrivee_id=arrivee["version_id"],
        reference_depart=reference_depart, reference_arrivee=reference_arrivee,
        origine_depart=depart, origine_arrivee=arrivee, type_lien=type_lien,
        justification=justification.strip(), auteur=utilisateur)
    lien.full_clean()
    lien.save()
    journaliser(utilisateur, "referentiel.correspondance_validee", lien,
        nouvelles={"depart": lien.depart_id, "arrivee": lien.arrivee_id, "type": type_lien, "annee": annee})
    return lien


@transaction.atomic
def retirer_correspondance(*, utilisateur, ecole, annee, lien_id, revision_attendue,
                          classe=None, adoption_attendue=None):
    _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    lien = CorrespondanceCompetence.objects.select_for_update().filter(pk=lien_id, ecole=ecole,
        annee_scolaire=annee, classe=classe).first()
    if lien is None:
        raise PermissionDenied
    if type(revision_attendue) is not int or lien.revision != revision_attendue or not lien.active:
        raise ValidationError("Ce lien a changé. Consultez à nouveau les correspondances.")
    lien.active, lien.retire_le, lien.retire_par = False, timezone.now(), utilisateur
    lien.revision += 1
    lien.save()
    journaliser(utilisateur, "referentiel.correspondance_retiree", lien, nouvelles={"revision": lien.revision})
    return lien
