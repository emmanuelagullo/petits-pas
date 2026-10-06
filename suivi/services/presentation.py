from django.core.exceptions import PermissionDenied
from django.db import transaction

from suivi.audit import instantane, journaliser
from suivi.autorisations import ADMINISTRER_ECOLE, MODIFIER_ETAT, autorise
from suivi.models import FormulationLocale, FormulationProposee, ReglagePresentation


def verifier_droit(utilisateur, ecole, classe=None):
    if classe is not None and classe.ecole_id != ecole.pk:
        raise PermissionDenied
    if classe:
        from suivi.referentiels import adoption_courante
        adoption = adoption_courante(classe)
        if adoption and adoption.clos:
            raise PermissionDenied("Les choix de cette classe sont clos.")
    if not autorise(utilisateur, MODIFIER_ETAT if classe else ADMINISTRER_ECOLE,
                    classe or ecole, ecole=ecole):
        raise PermissionDenied


@transaction.atomic
def enregistrer_reglage(utilisateur, reglage):
    verifier_droit(utilisateur, reglage.ecole, reglage.classe)
    precedent = ReglagePresentation.objects.filter(pk=reglage.pk).first() if reglage.pk else None
    champs = ("mode", "icone", "photo", "photo_pdf")
    anciennes = instantane(precedent, champs) if precedent else {}
    reglage.dernier_editeur = utilisateur
    reglage.full_clean()
    reglage.save()
    journaliser(utilisateur, "presentation.reglage", reglage, anciennes,
               nouvelles=instantane(reglage, champs))
    return reglage


@transaction.atomic
def enregistrer_formulation(*, utilisateur, competence, classe=None, cle=None, mode="remplacer", texte=""):
    ecole = competence.domaine.ecole
    verifier_droit(utilisateur, ecole, classe)
    filtres = {"ecole": ecole, "classe": classe, "competence": competence}
    locale = None
    if cle:
        try:
            type_source, identifiant = cle.split("-")
            identifiant = int(identifiant)
        except (ValueError, TypeError):
            raise PermissionDenied
        if type_source == "base":
            origine = FormulationProposee.objects.filter(pk=identifiant, competence=competence).first()
            if origine is None:
                raise PermissionDenied
            filtres["origine"] = origine
        elif type_source == "locale":
            origine = FormulationLocale.objects.filter(pk=identifiant, competence=competence,
                                                       ecole=ecole, origine__isnull=True,
                                                       origine_locale__isnull=True).first()
            if origine is None:
                raise PermissionDenied
            if origine.classe_id == (classe.pk if classe else None):
                locale = origine
            elif classe is not None and origine.classe_id is None:
                filtres["origine_locale"] = origine
            else:
                raise PermissionDenied
        else:
            raise PermissionDenied
        if locale is None:
            locale = FormulationLocale.objects.filter(**filtres).first()
    locale = locale or FormulationLocale(**filtres)
    anciennes = instantane(locale, ("mode", "texte")) if locale.pk else {}
    locale.mode = mode
    locale.texte = texte.strip()
    locale.dernier_editeur = utilisateur
    locale.full_clean()
    locale.save()
    journaliser(utilisateur, "presentation.formulation", locale, anciennes,
               instantane(locale, ("mode", "texte")))
    return locale
