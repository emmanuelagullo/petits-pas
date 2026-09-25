"""Sauvegardes complètes du paquet autonome, sans dépendance à Django."""

import hashlib
import json
import shutil
import sqlite3
import stat
import tempfile
import threading
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


FORMAT = "petits-pas-paquet"
VERSION = 1
TAILLE_MAX = 10 * 1024**3
FICHIERS_MAX = 100_000
_attente = None
_verrou_attente = threading.Lock()


def _empreinte(fichier):
    somme = hashlib.sha256()
    while bloc := fichier.read(1024 * 1024):
        somme.update(bloc)
    return somme.hexdigest()


def creer_sauvegarde(paquet, destination):
    """Écrire un ZIP cohérent de la base, de la clé et des médias."""
    with tempfile.TemporaryDirectory(prefix=".copie-sqlite-", dir=paquet.parent) as dossier:
        base = Path(dossier) / "carnet.sqlite3"
        with sqlite3.connect(paquet / "carnet.sqlite3") as origine:
            with sqlite3.connect(base) as copie:
                origine.backup(copie)
        fichiers = {
            "carnet.sqlite3": base,
            "secret-key": paquet / "secret-key",
        }
        if (paquet / "media").is_symlink():
            raise ValueError("Lien symbolique refusé pour le dossier des médias.")
        for chemin in sorted((paquet / "media").rglob("*")):
            if chemin.is_symlink():
                raise ValueError(f"Lien symbolique refusé dans les médias : {chemin}")
            if chemin.is_file():
                fichiers[chemin.relative_to(paquet).as_posix()] = chemin
        empreintes = {}
        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            for nom, chemin in fichiers.items():
                with chemin.open("rb") as source:
                    empreintes[nom] = _empreinte(source)
                archive.write(chemin, nom)
            archive.writestr(
                "manifest.json",
                json.dumps({"format": FORMAT, "version": VERSION, "files": empreintes}),
            )


def preparer_restauration(source, parent):
    """Valider le ZIP avant de préparer un nouveau paquet sans toucher à l'ancien."""
    with ZipFile(source) as archive:
        entrees = archive.infolist()
        noms = [entree.filename for entree in entrees]
        if len(noms) != len(set(noms)) or len(noms) > FICHIERS_MAX:
            raise ValueError("Archive trop volumineuse ou noms de fichiers répétés.")
        if "manifest.json" not in noms:
            raise ValueError("Manifeste du paquet absent.")
        if archive.getinfo("manifest.json").file_size > 1024 * 1024:
            raise ValueError("Manifeste trop volumineux.")
        manifeste = json.loads(archive.read("manifest.json"))
        if manifeste.get("format") != FORMAT or manifeste.get("version") != VERSION:
            raise ValueError("Format de sauvegarde inconnu.")
        attendus = manifeste.get("files")
        if not isinstance(attendus, dict) or not {"carnet.sqlite3", "secret-key"} <= attendus.keys():
            raise ValueError("Base ou clé absente de la sauvegarde.")
        if set(noms) != set(attendus) | {"manifest.json"}:
            raise ValueError("Le contenu ne correspond pas au manifeste.")
        if sum(e.file_size for e in entrees) > TAILLE_MAX:
            raise ValueError("La sauvegarde dépasse la taille autorisée.")

        etape = Path(tempfile.mkdtemp(prefix=".restauration-", dir=parent))
        try:
            for entree in entrees:
                nom = entree.filename
                if nom == "manifest.json":
                    continue
                elements = PurePosixPath(nom).parts
                if (
                    not elements or any(p in {"", ".", ".."} for p in elements)
                    or (nom not in {"carnet.sqlite3", "secret-key"} and elements[0] != "media")
                    or nom.startswith("/") or "\\" in nom or entree.is_dir()
                    or stat.S_ISLNK(entree.external_attr >> 16)
                ):
                    raise ValueError("Chemin invalide dans la sauvegarde.")
                cible = etape.joinpath(*elements)
                cible.parent.mkdir(parents=True, exist_ok=True)
                somme = hashlib.sha256()
                with archive.open(entree) as entree_zip, cible.open("xb") as sortie:
                    while bloc := entree_zip.read(1024 * 1024):
                        sortie.write(bloc)
                        somme.update(bloc)
                if somme.hexdigest() != attendus[nom]:
                    raise ValueError(f"Fichier altéré dans la sauvegarde : {nom}")
            if not (etape / "secret-key").read_text(encoding="utf-8").strip():
                raise ValueError("Clé vide dans la sauvegarde.")
            with sqlite3.connect(etape / "carnet.sqlite3") as connexion:
                if connexion.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Base SQLite endommagée.")
                if not connexion.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'django_migrations'"
                ).fetchone():
                    raise ValueError("La base ne contient pas les migrations Django.")
            (etape / "media").mkdir(exist_ok=True)
            (etape / "secret-key").chmod(0o600)
            return etape
        except BaseException:
            shutil.rmtree(etape)
            raise


def programmer_restauration(etape):
    global _attente
    with _verrou_attente:
        if _attente is not None:
            raise ValueError("Une restauration attend déjà la fermeture de l'application.")
        _attente = etape


def restauration_en_attente():
    with _verrou_attente:
        return _attente


def appliquer_restauration(paquet, etape):
    """Remplacer le paquet après l'arrêt du serveur, en gardant l'original."""
    if etape.parent != paquet.parent or not etape.is_dir():
        raise ValueError("Dossier de restauration invalide.")
    ancien = Path(tempfile.mkdtemp(prefix=f".{paquet.name}-avant-restauration-", dir=paquet.parent))
    ancien.rmdir()
    paquet.rename(ancien)
    try:
        etape.rename(paquet)
    except BaseException:
        ancien.rename(paquet)
        raise
    return ancien
