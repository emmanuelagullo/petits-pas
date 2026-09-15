import hashlib
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import CommandError

from .sauvegardes_medias import verifier as verifier_medias


FORMAT = "petits-pas-reprise"
VERSION = 1
MODES = {"online", "writes-suspended"}
TAILLE_BLOC = 1024 * 1024


def _hacher(chemin):
    somme = hashlib.sha256()
    taille = 0
    with chemin.open("rb") as fichier:
        while bloc := fichier.read(TAILLE_BLOC):
            somme.update(bloc)
            taille += len(bloc)
    return taille, somme.hexdigest()


def _horodatage(valeur, nom):
    try:
        date = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as erreur:
        raise CommandError(f"Horodatage invalide pour {nom} : {valeur!r}") from erreur
    if date.tzinfo is None:
        raise CommandError(f"Le fuseau horaire manque pour {nom}.")
    return date


def _fichier_unique(repertoire, motif, description):
    fichiers = list(repertoire.glob(motif))
    if len(fichiers) != 1 or not fichiers[0].is_file() or fichiers[0].is_symlink():
        raise CommandError(
            f"Un unique {description} est attendu dans {repertoire}."
        )
    return fichiers[0]


def _repertoire_unique(repertoire, motif, description):
    repertoires = list(repertoire.glob(motif))
    if (
        len(repertoires) != 1
        or not repertoires[0].is_dir()
        or repertoires[0].is_symlink()
    ):
        raise CommandError(
            f"Un unique {description} est attendu dans {repertoire}."
        )
    return repertoires[0]


def creer_manifeste(
    repertoire,
    mode,
    started_at,
    database_completed_at,
    media_completed_at,
    completed_at,
):
    repertoire = Path(repertoire)
    if not repertoire.is_absolute():
        raise CommandError("Le chemin du paquet de reprise doit être absolu.")
    if mode not in MODES:
        raise CommandError(f"Mode de sauvegarde inconnu : {mode}")
    if (repertoire / "manifest.json").exists():
        raise CommandError("Le manifeste global existe déjà.")

    dates = [
        _horodatage(started_at, "started_at"),
        _horodatage(database_completed_at, "database_completed_at"),
        _horodatage(media_completed_at, "media_completed_at"),
        _horodatage(completed_at, "completed_at"),
    ]
    if dates != sorted(dates):
        raise CommandError("Les étapes de sauvegarde ne sont pas chronologiques.")

    postgresql_dir = repertoire / "postgresql"
    medias_dir = repertoire / "medias"
    if (
        not postgresql_dir.is_dir()
        or postgresql_dir.is_symlink()
        or not medias_dir.is_dir()
        or medias_dir.is_symlink()
    ):
        raise CommandError("Les répertoires PostgreSQL ou médias sont invalides.")
    dump = _fichier_unique(postgresql_dir, "*.dump", "export PostgreSQL")
    somme_dump = _fichier_unique(
        postgresql_dir, "*.dump.sha256", "fichier SHA-256 PostgreSQL"
    )
    sauvegarde_medias = _repertoire_unique(
        medias_dir, "petits-pas-medias-*", "export de médias"
    )
    manifeste_medias = verifier_medias(sauvegarde_medias)

    taille_dump, sha_dump = _hacher(dump)
    _, sha_manifeste_medias = _hacher(sauvegarde_medias / "manifest.json")

    manifeste = {
        "format": FORMAT,
        "version": VERSION,
        "mode": mode,
        "started_at": started_at,
        "database_completed_at": database_completed_at,
        "media_completed_at": media_completed_at,
        "completed_at": completed_at,
        "postgresql": {
            "dump": dump.relative_to(repertoire).as_posix(),
            "sha256_file": somme_dump.relative_to(repertoire).as_posix(),
            "size": taille_dump,
            "sha256": sha_dump,
        },
        "media": {
            "directory": sauvegarde_medias.relative_to(repertoire).as_posix(),
            "manifest_sha256": sha_manifeste_medias,
            "objects": len(manifeste_medias["objects"]),
        },
    }
    (repertoire / "manifest.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifeste


def verifier(repertoire):
    repertoire = Path(repertoire)
    if not repertoire.is_absolute():
        raise CommandError("Le chemin du paquet de reprise doit être absolu.")
    if not repertoire.is_dir() or repertoire.is_symlink():
        raise CommandError(f"Paquet de reprise introuvable : {repertoire}")

    attendus = {"manifest.json", "postgresql", "medias"}
    presents = {chemin.name for chemin in repertoire.iterdir()}
    if presents != attendus:
        raise CommandError("Le contenu de premier niveau du paquet est inattendu.")

    manifeste_path = repertoire / "manifest.json"
    if not manifeste_path.is_file() or manifeste_path.is_symlink():
        raise CommandError("Le manifeste global est absent ou invalide.")
    try:
        manifeste = json.loads(manifeste_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise CommandError(f"Manifeste global illisible : {erreur}") from erreur

    if manifeste.get("format") != FORMAT or manifeste.get("version") != VERSION:
        raise CommandError("Format ou version du paquet non pris en charge.")
    if manifeste.get("mode") not in MODES:
        raise CommandError("Mode de cohérence absent ou invalide.")

    dates = [
        _horodatage(manifeste.get("started_at"), "started_at"),
        _horodatage(
            manifeste.get("database_completed_at"), "database_completed_at"
        ),
        _horodatage(manifeste.get("media_completed_at"), "media_completed_at"),
        _horodatage(manifeste.get("completed_at"), "completed_at"),
    ]
    if dates != sorted(dates):
        raise CommandError("Les étapes du paquet ne sont pas chronologiques.")

    postgresql = manifeste.get("postgresql")
    media = manifeste.get("media")
    if not isinstance(postgresql, dict) or not isinstance(media, dict):
        raise CommandError("Les sections PostgreSQL ou médias sont invalides.")

    dump_relatif = postgresql.get("dump")
    somme_relative = postgresql.get("sha256_file")
    media_relatif = media.get("directory")
    if not all(
        isinstance(valeur, str)
        for valeur in (dump_relatif, somme_relative, media_relatif)
    ):
        raise CommandError("Les chemins du manifeste sont invalides.")

    dump = repertoire / dump_relatif
    somme_dump = repertoire / somme_relative
    postgresql_dir = repertoire / "postgresql"
    medias_dir = repertoire / "medias"
    if (
        not postgresql_dir.is_dir()
        or postgresql_dir.is_symlink()
        or not medias_dir.is_dir()
        or medias_dir.is_symlink()
        or dump.parent != postgresql_dir
        or somme_dump.parent != postgresql_dir
        or not dump.is_file()
        or dump.is_symlink()
        or not somme_dump.is_file()
        or somme_dump.is_symlink()
    ):
        raise CommandError("Les fichiers PostgreSQL du manifeste sont invalides.")
    elements_postgresql = {chemin.name for chemin in postgresql_dir.iterdir()}
    if elements_postgresql != {dump.name, somme_dump.name}:
        raise CommandError("Le répertoire PostgreSQL contient des fichiers inattendus.")

    taille_dump, sha_dump = _hacher(dump)
    if postgresql.get("size") != taille_dump or postgresql.get("sha256") != sha_dump:
        raise CommandError("La taille ou la somme SHA-256 PostgreSQL est incorrecte.")
    morceaux = somme_dump.read_text(encoding="utf-8").strip().split(maxsplit=1)
    if len(morceaux) != 2 or morceaux[0] != sha_dump or morceaux[1] != dump.name:
        raise CommandError("Le fichier SHA-256 PostgreSQL est incohérent.")

    sauvegarde_medias = repertoire / media_relatif
    if sauvegarde_medias.parent != medias_dir:
        raise CommandError("Le chemin des médias du manifeste est invalide.")
    repertoires_medias = [chemin for chemin in medias_dir.iterdir()]
    if repertoires_medias != [sauvegarde_medias]:
        raise CommandError("Le répertoire médias contient des éléments inattendus.")
    manifeste_medias = verifier_medias(sauvegarde_medias)
    _, sha_manifeste_medias = _hacher(sauvegarde_medias / "manifest.json")
    if media.get("manifest_sha256") != sha_manifeste_medias:
        raise CommandError("La somme du manifeste des médias est incorrecte.")
    if media.get("objects") != len(manifeste_medias["objects"]):
        raise CommandError("Le nombre d’objets médias est incorrect.")

    return manifeste, dump
