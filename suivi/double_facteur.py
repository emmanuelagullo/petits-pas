"""Exigence de 2FA d'un compte, calculée à partir de la politique du déployeur,
de celle de chaque école et des fonctions actives (jamais stockée).

Chaque niveau pose « obligatoire jusqu'au rang n » et « désactivé à partir du
rang m » (voir carnet.double_facteur). Un niveau inférieur ne baisse jamais une
obligation reçue et ne rouvre jamais ce qui est désactivé au-dessus. Si une
politique d'école devient incompatible avec celle du déployeur après coup, le
niveau supérieur l'emporte et un avertissement le signale ; rien n'est modifié
en base.
"""
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.utils import timezone

from carnet.double_facteur import (
    ASSOCIE, CONTRIBUTEUR, DIRECTION, RESPONSABLE, SANS_FONCTION,
)
from comptes.models import AffectationClasse

from .autorisations import (
    affectations_actives, appartenances_actives, responsabilites_direction_actives,
)
from .models import PolitiqueDoubleFacteurEcole

RANG_PAR_TYPE_AFFECTATION = {
    AffectationClasse.RESPONSABLE: RESPONSABLE,
    AffectationClasse.ENSEIGNANT_ASSOCIE: ASSOCIE,
    AffectationClasse.CONTRIBUTEUR: CONTRIBUTEUR,
}


class Exigence(str, Enum):
    OBLIGATOIRE = "obligatoire"
    OPTIONNELLE = "optionnelle"
    DESACTIVEE = "desactivee"


@dataclass(frozen=True)
class PolitiqueEffective:
    obligatoire_jusqu_au_rang: int
    desactive_a_partir_du_rang: int
    avertissements: tuple = ()

    def exigence_pour_rang(self, rang):
        if rang <= self.obligatoire_jusqu_au_rang:
            return Exigence.OBLIGATOIRE
        if rang >= self.desactive_a_partir_du_rang:
            return Exigence.DESACTIVEE
        return Exigence.OPTIONNELLE


def politique_deployeur():
    if not settings.DOUBLE_FACTEUR_DISPONIBLE:
        # Sans dépendances, sans clé de chiffrement ou en mode local, la
        # fonction n'existe pas : elle est désactivée pour tout le monde.
        return PolitiqueEffective(0, DIRECTION)
    return PolitiqueEffective(
        settings.DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG,
        settings.DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG,
    )


def combiner(deployeur, obligatoire_ecole=0, desactive_ecole=6):
    """Politique effective d'une école sous celle du déployeur.

    Le niveau supérieur l'emporte aussi bien pour l'obligation (qu'on ne baisse
    pas) que pour la désactivation (qu'on ne rouvre pas).
    """
    n_d = deployeur.obligatoire_jusqu_au_rang
    m_d = deployeur.desactive_a_partir_du_rang
    avertissements = []
    n_ecole = min(obligatoire_ecole, m_d - 1)
    if n_ecole < obligatoire_ecole:
        avertissements.append(
            "Une partie de l'obligation de l'école est sans effet : le "
            "déployeur a désactivé le 2FA pour ces fonctions."
        )
    n = max(n_d, n_ecole)
    m = max(min(m_d, desactive_ecole), n + 1)
    if desactive_ecole <= n:
        avertissements.append(
            "Une désactivation de l'école est sans effet : le 2FA est "
            "obligatoire pour ces fonctions au niveau supérieur."
        )
    return PolitiqueEffective(n, m, tuple(avertissements))


def politique_ecole(ecole):
    """Politique effective de l'école (déployeur et école combinés)."""
    stockee = PolitiqueDoubleFacteurEcole.objects.filter(ecole=ecole).first()
    if stockee is None:
        return combiner(politique_deployeur())
    return combiner(
        politique_deployeur(),
        stockee.obligatoire_jusqu_au_rang,
        stockee.desactive_a_partir_du_rang,
    )


def rangs_par_ecole(utilisateur, date=None):
    """Rang le plus haut de la personne dans chaque école où elle est active.

    Les fonctions suivent l'accès réellement accordé : une affectation sur une
    classe encore en préparation, ou une pré-attribution d'invitation, ne
    compte pas. Une appartenance sans fonction vaut SANS_FONCTION.
    """
    date = date or timezone.localdate()
    rangs = {a.ecole_id: SANS_FONCTION for a in appartenances_actives(utilisateur, date=date)}
    for ecole_id in responsabilites_direction_actives(utilisateur, date=date).values_list(
            "appartenance__ecole_id", flat=True):
        rangs[ecole_id] = DIRECTION
    for ecole_id, type_affectation in affectations_actives(utilisateur, date=date).values_list(
            "appartenance__ecole_id", "type"):
        rang = RANG_PAR_TYPE_AFFECTATION[type_affectation]
        rangs[ecole_id] = min(rangs.get(ecole_id, SANS_FONCTION), rang)
    return rangs


def rang_le_plus_haut(utilisateur, date=None):
    """Rang le plus haut toutes écoles confondues (SANS_FONCTION sans école)."""
    return min(rangs_par_ecole(utilisateur, date).values(), default=SANS_FONCTION)


def exigence_double_facteur(utilisateur, date=None):
    """Exigence effective d'un compte.

    L'obligation d'une seule école suffit. La fonction n'est retirée que si
    toutes les écoles de la personne la désactivent pour son rang. Sans
    appartenance active, seule la politique du déployeur s'applique, au rang
    SANS_FONCTION.
    """
    if not (utilisateur and getattr(utilisateur, "is_authenticated", False) and utilisateur.is_active):
        return Exigence.DESACTIVEE
    rangs = rangs_par_ecole(utilisateur, date)
    if not rangs:
        return politique_deployeur().exigence_pour_rang(SANS_FONCTION)
    stockees = {p.ecole_id: p for p in PolitiqueDoubleFacteurEcole.objects.filter(ecole_id__in=rangs)}
    deployeur = politique_deployeur()
    exigences = set()
    for ecole_id, rang in rangs.items():
        stockee = stockees.get(ecole_id)
        politique = combiner(
            deployeur,
            stockee.obligatoire_jusqu_au_rang if stockee else 0,
            stockee.desactive_a_partir_du_rang if stockee else 6,
        )
        exigences.add(politique.exigence_pour_rang(rang))
    if Exigence.OBLIGATOIRE in exigences:
        return Exigence.OBLIGATOIRE
    if Exigence.OPTIONNELLE in exigences:
        return Exigence.OPTIONNELLE
    return Exigence.DESACTIVEE
