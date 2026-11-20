"""Clé de secours d'un compte sur une installation locale.

Elle reprend la forme des codes de secours du second facteur (seize signes
sans ambiguïté, soit 80 bits) : une empreinte SHA-256 suffit à en protéger la
base. Chaque compte n'a qu'une clé ; en créer une nouvelle remplace l'ancienne.
Ce module ne journalise rien et ne ferme aucune session : voir
`suivi.services.acces_local`.
"""
from django.db import transaction

from pas_communs.authentification import totp as moteur

from .models import CleSecoursLocale


def _empreinte(cle_normalisee):
    return moteur.empreinte_code_secours(cle_normalisee)


def normaliser_cle(saisie):
    """Majuscules, sans espaces ni tirets ; None si la forme est impossible."""
    return moteur.normaliser_code_secours(saisie)


def creer_cle(utilisateur):
    """Remplace la clé du compte et retourne la nouvelle, prête à afficher une fois."""
    cle = moteur.nouveau_code_secours()
    with transaction.atomic():
        CleSecoursLocale.objects.update_or_create(
            utilisateur=utilisateur, defaults={"empreinte": _empreinte(cle)})
    return moteur.presenter_code_secours(cle)


def compte_par_cle(saisie):
    """Compte actif auquel appartient cette clé, ou None."""
    cle = normaliser_cle(saisie)
    if cle is None:
        return None
    ligne = (CleSecoursLocale.objects.select_related("utilisateur")
             .filter(empreinte=_empreinte(cle), utilisateur__is_active=True).first())
    return ligne.utilisateur if ligne else None


def cle_correspond(utilisateur, saisie):
    """Vrai si la saisie est la clé actuelle de ce compte (preuve de saisie)."""
    cle = normaliser_cle(saisie)
    if cle is None:
        return False
    return CleSecoursLocale.objects.filter(
        utilisateur=utilisateur, empreinte=_empreinte(cle)).exists()


def possede_une_cle(utilisateur):
    return CleSecoursLocale.objects.filter(utilisateur=utilisateur).exists()
