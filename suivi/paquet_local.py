"""Adaptation Petits Pas du moteur Pas communs ; API et état local conservés."""
import json
import shutil
import threading
from datetime import datetime, timezone

from pas_communs import paquets as moteur
from pas_communs.paquets import (
    Preparation, ProfilPaquet, VERSION, TAILLE_MAX, FICHIERS_MAX, RESULTAT,
    appliquer_restauration, lire_resultat,
)

FORMAT = "petits-pas-paquet"
PROFIL = ProfilPaquet("petits-pas", FORMAT, "carnet.sqlite3", accepter_sans_application=True)
SUIVI_SAUVEGARDE = "suivi-sauvegarde.json"
_attente = None
_preparation = None
_verrou_attente = threading.Lock()


def creer_sauvegarde(paquet, destination, *, taille_bloc=None, export_ecole=None,
                     export_classe=None, fichiers_externes=None):
    metadonnees = {}
    if export_ecole is not None:
        metadonnees["export_ecole"] = export_ecole
    if export_classe is not None:
        metadonnees["export_classe"] = export_classe
    return moteur.creer_sauvegarde(paquet, destination, profil=PROFIL,
        taille_bloc=taille_bloc, metadonnees=metadonnees, fichiers_externes=fichiers_externes)


def preparer_restauration(source, parent, nom_paquet="paquet-autonome", *,
                         taille_max=TAILLE_MAX, fichiers_max=FICHIERS_MAX,
                         migrations_connues=None):
    return moteur.preparer_restauration(source, parent, nom_paquet, profil=PROFIL,
        taille_max=taille_max, fichiers_max=fichiers_max, migrations_connues=migrations_connues)


def iterer_restauration(source, parent, nom_paquet="paquet-autonome", *,
                       taille_max=TAILLE_MAX, fichiers_max=FICHIERS_MAX,
                       migrations_connues=None, ouvrir_destination=None):
    return moteur.iterer_restauration(source, parent, nom_paquet, profil=PROFIL,
        taille_max=taille_max, fichiers_max=fichiers_max, migrations_connues=migrations_connues,
        ouvrir_destination=ouvrir_destination)


def noter_export(paquet):
    """Un ZIP préparé n'est pas la preuve d'une copie conservée hors appareil."""
    instant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    temporaire = paquet / (SUIVI_SAUVEGARDE + ".tmp")
    temporaire.write_text(json.dumps({"prepare_le": instant}), encoding="utf-8")
    temporaire.replace(paquet / SUIVI_SAUVEGARDE)


def suivi_export(paquet, maintenant=None):
    """Information propre à cet appareil, absente des ZIP de transfert."""
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        valeur = json.loads((paquet / SUIVI_SAUVEGARDE).read_text(encoding="utf-8"))["prepare_le"]
        instant = datetime.fromisoformat(valeur)
        if instant.tzinfo is None or instant > maintenant:
            raise ValueError("Date invalide")
    except (OSError, ValueError, KeyError, TypeError):
        return {"dernier_export_local": None, "rappel_sauvegarde_local": True}
    return {"dernier_export_local": instant,
            "rappel_sauvegarde_local": (maintenant - instant).total_seconds() >= 7 * 86400}


def retenir_preparation(preparation):
    global _preparation
    with _verrou_attente:
        if _attente is not None or _preparation is not None:
            raise ValueError("Une restauration est déjà en préparation.")
        _preparation = preparation


def preparation_en_attente():
    with _verrou_attente:
        return _preparation


def annuler_preparation():
    global _preparation
    with _verrou_attente:
        preparation = _preparation
        _preparation = None
    if preparation is not None:
        shutil.rmtree(preparation.etape)


def confirmer_restauration():
    global _preparation, _attente
    with _verrou_attente:
        if _preparation is None or _attente is not None:
            raise ValueError("Aucune restauration à confirmer.")
        _attente = _preparation
        _preparation = None
        return _attente


def restauration_en_attente():
    with _verrou_attente:
        return _attente
