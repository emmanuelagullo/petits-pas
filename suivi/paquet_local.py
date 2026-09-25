"""Sauvegardes complètes du paquet autonome, sans dépendance à Django."""

import hashlib
import json
import shutil
import sqlite3
import stat
import tempfile
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


FORMAT = "petits-pas-paquet"
VERSION = 1
TAILLE_MAX = 10 * 1024**3
FICHIERS_MAX = 100_000
_attente = None
_preparation = None
_verrou_attente = threading.Lock()
RESULTAT = "resultat-restauration.json"


@dataclass(frozen=True)
class Preparation:
    etape: Path
    date_sauvegarde: str | None
    ancien: Path
    nom_archive: str
    nombre_medias: int


def _empreinte(fichier):
    somme = hashlib.sha256()
    while bloc := fichier.read(1024 * 1024):
        somme.update(bloc)
    return somme.hexdigest()


def creer_sauvegarde(paquet, destination):
    """Écrire un ZIP cohérent de la base, de la clé et des médias."""
    with tempfile.TemporaryDirectory(prefix=".copie-sqlite-", dir=paquet.parent) as dossier:
        base = Path(dossier) / "carnet.sqlite3"
        with closing(sqlite3.connect(paquet / "carnet.sqlite3")) as origine:
            with closing(sqlite3.connect(base)) as copie:
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
                json.dumps({
                    "format": FORMAT, "version": VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "files": empreintes,
                }),
            )


def preparer_restauration(source, parent, nom_paquet="paquet-autonome"):
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
        date_sauvegarde = manifeste.get("created_at")
        if date_sauvegarde is not None:
            try:
                date_sauvegarde = datetime.fromisoformat(date_sauvegarde).isoformat()
            except (TypeError, ValueError) as exc:
                raise ValueError("Date de sauvegarde invalide.") from exc
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
            with closing(sqlite3.connect(etape / "carnet.sqlite3")) as connexion:
                if connexion.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Base SQLite endommagée.")
                if not connexion.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'django_migrations'"
                ).fetchone():
                    raise ValueError("La base ne contient pas les migrations Django.")
            (etape / "media").mkdir(exist_ok=True)
            (etape / "secret-key").chmod(0o600)
            ancien = parent / (
                f".{nom_paquet}-avant-restauration-"
                f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
            )
            return Preparation(
                etape, date_sauvegarde, ancien,
                Path(getattr(source, "name", "sauvegarde.zip")).name,
                sum(nom.startswith("media/") for nom in attendus),
            )
        except BaseException:
            shutil.rmtree(etape)
            raise


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


def appliquer_restauration(paquet, preparation):
    """Remplacer le paquet après l'arrêt du serveur, en gardant l'original."""
    etape = preparation.etape
    ancien = preparation.ancien
    if (etape.parent != paquet.parent or not etape.is_dir()
            or ancien.parent != paquet.parent or ancien.exists()):
        raise ValueError("Dossier de restauration invalide.")
    (etape / RESULTAT).write_text(json.dumps({
        "date_sauvegarde": preparation.date_sauvegarde,
        "nom_archive": preparation.nom_archive,
        "nombre_medias": preparation.nombre_medias,
        "ancien": str(ancien),
        "applique_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }), encoding="utf-8")
    paquet.rename(ancien)
    try:
        etape.rename(paquet)
    except BaseException:
        ancien.rename(paquet)
        raise
    return ancien


def lire_resultat(paquet):
    chemin = paquet / RESULTAT
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None
