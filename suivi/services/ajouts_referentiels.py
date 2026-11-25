"""Ajouts locaux et reprises explicites, sans copie des acquisitions."""
from uuid import uuid4
from base64 import urlsafe_b64encode

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from suivi.audit import journaliser
from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise
from suivi.models import (AdoptionReferentiel, Classe, Competence, CompetenceLocale,
                         DisponibiliteCompetenceLocale, Domaine, Ecole, FormulationProposee, RubriqueClasse, SousDomaine)
from suivi.rubriques import contenu_classement
from suivi.adaptations_referentiels import contenus_ecole
from .choix_bases_referentiels import verifier_annee


def _verrouiller(utilisateur, ecole, annee, classe=None, adoption_attendue=None):
    verifier_annee(annee)
    if not autorise(utilisateur, GERER_REFERENTIEL_CLASSE if classe else GERER_REFERENTIEL_ECOLE,
                   classe if classe else ecole):
        raise PermissionDenied
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    if classe:
        classe = Classe.objects.select_for_update().get(pk=classe.pk)
        if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee:
            raise PermissionDenied
        adoption = AdoptionReferentiel.objects.filter(classe=classe, courante=True).select_related("version").first()
        if not adoption or adoption.clos:
            raise ValidationError("Choisissez une base pour une classe ouverte avant d'ajouter une compétence.")
        if adoption.pk != adoption_attendue:
            raise ValidationError("La base a changé. Consultez à nouveau les ajouts.")
        return adoption


def catalogue_reprises(*, utilisateur, ecole, annee, classe):
    """Propositions de l'année, et ajouts déjà utilisés dans une classe gérée."""
    if classe.ecole_id != ecole.pk or classe.annee_scolaire != annee or not autorise(
            utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    classes = [c.pk for c in Classe.objects.filter(ecole=ecole, annee_scolaire__lte=annee)
               if autorise(utilisateur, GERER_REFERENTIEL_CLASSE, c)]
    return CompetenceLocale.objects.filter(ecole=ecole, suivi_libre=False).filter(
        Q(disponibilites__annee_scolaire=annee, disponibilites__classe__isnull=True) |
        Q(disponibilites__classe_id__in=classes)).distinct().order_by("pk")


def definition_sous_domaine(sous):
    return {"id": sous.pk, "code": sous.code, "nom": sous.nom,
            "domaine_id": sous.domaine_id, "ordre": sous.ordre}


def classement_local(ecole, contenus, domaine_id, sous_domaine_id, suivi_libre, classe=None):
    domaine = next((d for c in contenus for d in c.get("domaines", []) if d["id"] == domaine_id), None)
    if domaine is None:
        raise ValidationError("Choisissez un domaine de la base consultée.")
    sous = next((s for c in contenus for s in c.get("sous_domaines", [])
                 if s["id"] == sous_domaine_id and s["domaine_id"] == domaine_id), None)
    if sous_domaine_id is not None and sous is None:
        raise ValidationError("Choisissez un sous-domaine de ce domaine.")
    personnalise = classe and RubriqueClasse.objects.filter(classe=classe, creee=True).filter(
        Q(domaine_id=domaine_id, sous_domaine__isnull=True) | Q(sous_domaine_id=sous_domaine_id, sous_domaine__isnull=False)
    ).exists()
    if suivi_libre or personnalise or domaine["code"].startswith("ajout-"):
        groupe = Domaine.objects.get(pk=domaine_id, ecole=ecole)
        return groupe, SousDomaine.objects.get(pk=sous["id"], domaine=groupe) if sous else None
    # Les ajouts au référentiel gardent leur groupe lors d'un changement de base.
    nom = "Ajouts — " + domaine["nom"][:191]
    groupe = Domaine.objects.filter(ecole=ecole, code__startswith="ajout-", nom=nom).first()
    if groupe is None:
        groupe = Domaine.objects.create(ecole=ecole, code="ajout-" + uuid4().hex[:14], nom=nom, ordre=domaine["ordre"])
    local = None
    if sous:
        local = SousDomaine.objects.filter(domaine=groupe, nom=sous["nom"]).first()
        if local is None:
            local = SousDomaine.objects.create(domaine=groupe, code="ajout-" + uuid4().hex[:14],
                                               nom=sous["nom"], ordre=sous["ordre"])
    return groupe, local


def utilisations_classement(locale):
    return list(locale.disponibilites.select_related("classe").order_by("annee_scolaire", "classe_id", "pk"))


def peut_corriger_classement(utilisateur, locale, classe, utilisations):
    if autorise(utilisateur, GERER_REFERENTIEL_ECOLE, locale.ecole):
        return True
    return bool(classe and utilisations and all(u.classe_id == classe.pk for u in utilisations)
                and autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe))


@transaction.atomic
def corriger_classement(*, utilisateur, locale, annee, classe, adoption_attendue, niveau, domaine_id,
                        sous_domaine_id, etat_attendu):
    adoption = _verrouiller(utilisateur, locale.ecole, annee, classe, adoption_attendue)
    utilisations = utilisations_classement(locale)
    if not peut_corriger_classement(utilisateur, locale, classe, utilisations):
        raise PermissionDenied
    competence = Competence.objects.select_for_update().get(pk=locale.competence_id)
    avant = etat_classement(competence, utilisations)
    if avant != etat_attendu:
        raise ValidationError("Le classement ou les utilisations ont changé. Rechargez la page.")
    if niveau not in ("PS", "MS", "GS"):
        raise ValidationError("Choisissez une section.")
    if domaine_id is not None:
        contenus = [contenu_classement(adoption)] if adoption else [c for _, c in contenus_ecole(locale.ecole, annee)]
        competence.domaine, competence.sous_domaine = classement_local(
            locale.ecole, contenus, domaine_id, sous_domaine_id, locale.suivi_libre, classe)
    elif sous_domaine_id is not None:
        raise ValidationError("Choisissez d’abord le domaine du sous-domaine.")
    competence.niveau = niveau
    apres = etat_classement(competence, utilisations)
    if apres != avant:
        competence.save(update_fields=["niveau", "domaine", "sous_domaine"])
        journaliser(utilisateur, "referentiel.classement_corrige", locale, anciennes=avant, nouvelles=apres)


def etat_classement(competence, utilisations):
    return {"niveau": competence.niveau, "domaine": competence.domaine_id,
            "sous_domaine": competence.sous_domaine_id, "utilisations": [u.pk for u in utilisations]}


@transaction.atomic
def creer_ajout(*, utilisateur, ecole, annee, domaine_id, libelle, niveau, classe=None, adoption_attendue=None, suivi_libre=False, sous_domaine_id=None, variante_de=None, icone="", icone_png="", formulations=()):
    adoption = _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    contenus = [contenu_classement(adoption)] if classe else [c for _, c in contenus_ecole(ecole, annee)]
    if not isinstance(libelle, str) or not libelle.strip() or len(libelle.strip()) > 300:
        raise ValidationError("Précisez un libellé de 1 à 300 caractères.")
    if niveau not in ("PS", "MS", "GS"):
        raise ValidationError("Choisissez une section.")
    if suivi_libre and classe is None:
        raise PermissionDenied
    groupe, sous = classement_local(ecole, contenus, domaine_id, sous_domaine_id, suivi_libre, classe)
    competence = Competence(domaine=groupe, sous_domaine=sous, code="local-" + uuid4().hex[:24],
                            libelle=libelle.strip(), niveau=niveau, icone=icone)
    competence.full_clean()
    competence.save()
    definition = {"domaines": [{"id": groupe.pk, "code": groupe.code, "nom": groupe.nom, "ordre": groupe.ordre}],
        "competences": [{"id": competence.pk, "domaine_id": groupe.pk, "sous_domaine_id": competence.sous_domaine_id,
            "code": competence.code, "libelle": competence.libelle, "niveau": niveau, "icone": icone, "ordre": 0,
            "active": True, "cle_definition": f"locale-{competence.pk}"}]}
    definition["sous_domaines"] = [definition_sous_domaine(sous)] if sous else []
    portable = urlsafe_b64encode(uuid4().bytes).decode("ascii").rstrip("=")
    definition["identite_portable"] = "pp-" + portable
    if variante_de is not None:
        if classe is None or suivi_libre:
            raise PermissionDenied
        definition["variante_de"] = variante_de
    if icone_png or formulations:
        if variante_de is None:
            raise PermissionDenied
        if icone_png:
            from suivi.icones_partagees import conserver_png, decoder_icone, png_en_ligne
            from suivi.models import IconePartagee
            decoder_icone(png_en_ligne(icone_png))
            definition["competences"][0]["icone_png"] = icone_png
            conserver_png(definition, IconePartagee)
        if formulations:
            definition["formulations"] = []
            for ordre, texte in enumerate(formulations):
                formulation = FormulationProposee.objects.create(
                    competence=competence, code=f"F{ordre + 1}", texte=texte, ordre=ordre,
                )
                definition["formulations"].append({
                    "id": formulation.pk, "competence_id": competence.pk, "code": formulation.code,
                    "texte": texte, "ordre": ordre, "active": True,
                })
    locale = CompetenceLocale(suivi_libre=suivi_libre, ecole=ecole, competence=competence, classe_origine=classe,
                             auteur=utilisateur, definition=definition)
    locale.full_clean()
    locale.save()
    choix = DisponibiliteCompetenceLocale(locale=locale, annee_scolaire=annee, classe=classe, auteur=utilisateur)
    choix.full_clean()
    choix.save()
    journaliser(utilisateur, "referentiel.ajout_cree", locale,
                nouvelles={"competence": competence.pk, "classe": classe.pk if classe else None, "annee": annee})
    return locale


@transaction.atomic
def proposer_ajout(*, utilisateur, ecole, annee, locale):
    _verrouiller(utilisateur, ecole, annee)
    if locale.ecole_id != ecole.pk or locale.suivi_libre:
        raise PermissionDenied
    choix, nouveau = DisponibiliteCompetenceLocale.objects.get_or_create(locale=locale, annee_scolaire=annee,
        classe=None, defaults={"auteur": utilisateur})
    if nouveau:
        choix.full_clean()
        journaliser(utilisateur, "referentiel.ajout_propose", choix, nouvelles={"annee": annee})
    return choix


@transaction.atomic
def reprendre_ajout(*, utilisateur, ecole, annee, classe, locale, adoption_attendue):
    _verrouiller(utilisateur, ecole, annee, classe, adoption_attendue)
    if not catalogue_reprises(utilisateur=utilisateur, ecole=ecole, annee=annee, classe=classe).filter(pk=locale.pk).exists():
        raise PermissionDenied
    choix, nouveau = DisponibiliteCompetenceLocale.objects.get_or_create(locale=locale, classe=classe,
        defaults={"annee_scolaire": annee, "auteur": utilisateur})
    if nouveau:
        choix.full_clean()
        journaliser(utilisateur, "referentiel.ajout_repris", choix, nouvelles={"annee": annee, "classe": classe.pk})
    return choix
