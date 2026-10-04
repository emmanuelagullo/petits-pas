"""Copie validée indépendante : jamais une restauration de l'école courante."""
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock
from .paquet_local import preparer_restauration

MARQUEUR = "apercu-zip.json"
_verrou = RLock()
_preparation = None
_ouverture = False


def preparation():
    with _verrou:
        return _preparation


def preparer(archive, parent, **limites):
    global _preparation
    with _verrou:
        if _preparation is not None:
            raise ValueError("Une copie est déjà prête : ouvrez-la ou annulez.")
        copie = preparer_restauration(archive, parent, "apercu-zip", **limites)
        try:
            # Une copie exige sa propre connexion ; ne réutiliser aucune session
            # de l'école d'origine, même si un navigateur possède son cookie.
            with closing(sqlite3.connect(copie.etape / "carnet.sqlite3")) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='django_session'").fetchone():
                    db.execute("DELETE FROM django_session")
                    db.commit()
            (copie.etape / MARQUEUR).write_text(json.dumps({"format": "petits-pas-apercu",
                "archive": copie.nom_archive}), encoding="utf-8")
        except BaseException:
            shutil.rmtree(copie.etape)
            raise
        _preparation = copie
        return copie


def demander_ouverture():
    global _ouverture
    with _verrou:
        if _preparation is None:
            raise ValueError("Aucune copie à ouvrir.")
        _ouverture = True


def ouverture_demandee():
    with _verrou:
        return _ouverture


def detacher():
    """Transférer la copie au lanceur, qui en devient responsable."""
    global _preparation, _ouverture
    with _verrou:
        copie = _preparation
        _preparation = None
        _ouverture = False
        return copie


def annuler():
    copie = detacher()
    if copie:
        shutil.rmtree(copie.etape)


def verifier_dossier(dossier, habituel, essai):
    dossier = Path(dossier)
    if dossier.is_symlink() or dossier.resolve() in {Path(habituel).resolve(), Path(essai).resolve()}:
        raise ValueError("La copie à vérifier doit être distincte des autres écoles.")
    notice = json.loads((dossier / MARQUEUR).read_text(encoding="utf-8"))
    if not isinstance(notice, dict) or notice.get("format") != "petits-pas-apercu":
        raise ValueError("Ce dossier n'est pas une copie à vérifier.")
    if not (dossier / "carnet.sqlite3").is_file() or not (dossier / "secret-key").is_file():
        raise ValueError("Copie à vérifier incomplète.")
    return dossier.resolve()


def derniere_copie(parent, habituel, essai):
    candidates = []
    for dossier in Path(parent).glob(".restauration-*"):
        try:
            candidates.append((dossier.joinpath(MARQUEUR).stat().st_mtime_ns,
                               verifier_dossier(dossier, habituel, essai)))
        except (ValueError, OSError):
            continue
    return max(candidates, default=(0, None))[1]
