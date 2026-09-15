import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from django.core.files import File
from django.core.management.base import CommandError


FORMAT = "petits-pas-medias"
VERSION = 1
TAILLE_BLOC = 1024 * 1024


def _nom_valide(nom):
    chemin = PurePosixPath(nom)
    return (
        bool(nom)
        and not chemin.is_absolute()
        and "\\" not in nom
        and chemin.as_posix() == nom
        and all(partie not in ("", ".", "..") for partie in chemin.parts)
    )


def _chemin_objet(racine, nom):
    if not _nom_valide(nom):
        raise CommandError(f"Nom d’objet dangereux ou invalide : {nom!r}")
    return racine.joinpath(*PurePosixPath(nom).parts)


def _iterer_objets(stockage, repertoire=""):
    try:
        sous_repertoires, fichiers = stockage.listdir(repertoire)
    except FileNotFoundError as erreur:
        if not repertoire:
            return
        raise CommandError(
            f"Répertoire absent dans le stockage : {repertoire}"
        ) from erreur
    except Exception as erreur:
        cible = repertoire or "la racine"
        raise CommandError(f"Impossible de lister {cible} : {erreur}") from erreur

    for fichier in sorted(fichiers):
        nom = f"{repertoire}/{fichier}" if repertoire else fichier
        if not _nom_valide(nom):
            raise CommandError(f"Nom d’objet dangereux ou invalide : {nom!r}")
        yield nom

    for sous_repertoire in sorted(sous_repertoires):
        nom = (
            f"{repertoire}/{sous_repertoire}"
            if repertoire
            else sous_repertoire
        )
        if not _nom_valide(nom):
            raise CommandError(f"Nom de répertoire dangereux ou invalide : {nom!r}")
        yield from _iterer_objets(stockage, nom)


def _copier_et_hacher(source, destination):
    somme = hashlib.sha256()
    taille = 0
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("wb") as sortie:
        while bloc := source.read(TAILLE_BLOC):
            sortie.write(bloc)
            somme.update(bloc)
            taille += len(bloc)

    return taille, somme.hexdigest()


def _hacher_fichier(chemin):
    somme = hashlib.sha256()
    taille = 0
    with chemin.open("rb") as fichier:
        while bloc := fichier.read(TAILLE_BLOC):
            somme.update(bloc)
            taille += len(bloc)
    return taille, somme.hexdigest()


def sauvegarder(stockage, destination):
    destination = Path(destination)
    if not destination.is_absolute():
        raise CommandError("Le chemin de sauvegarde doit être absolu.")
    if destination.exists():
        raise CommandError(f"La destination existe déjà : {destination}")

    temporaire = destination.with_name(
        f".{destination.name}.incomplete-{uuid4()}"
    )
    objets_dir = temporaire / "objets"
    entrees = []

    try:
        objets_dir.mkdir(parents=True)
        for nom in _iterer_objets(stockage):
            chemin = _chemin_objet(objets_dir, nom)
            try:
                with stockage.open(nom, "rb") as source:
                    taille, somme = _copier_et_hacher(source, chemin)
            except Exception as erreur:
                if isinstance(erreur, CommandError):
                    raise
                raise CommandError(
                    f"Impossible de sauvegarder {nom!r} : {erreur}"
                ) from erreur
            entrees.append(
                {"name": nom, "size": taille, "sha256": somme}
            )

        manifeste = {
            "format": FORMAT,
            "version": VERSION,
            "created_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "objects": entrees,
        }
        (temporaire / "manifest.json").write_text(
            json.dumps(manifeste, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        temporaire.rename(destination)
    except Exception:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise

    return manifeste


def verifier(source):
    source = Path(source)
    manifeste_path = source / "manifest.json"
    objets_dir = source / "objets"

    if not source.is_absolute():
        raise CommandError("Le chemin de sauvegarde doit être absolu.")
    if source.is_symlink():
        raise CommandError(f"La sauvegarde ne peut pas être un lien : {source}")
    if not manifeste_path.is_file() or manifeste_path.is_symlink():
        raise CommandError(f"Manifeste introuvable : {manifeste_path}")
    if not objets_dir.is_dir() or objets_dir.is_symlink():
        raise CommandError(f"Répertoire d’objets introuvable : {objets_dir}")

    for chemin in objets_dir.rglob("*"):
        if chemin.is_symlink():
            raise CommandError(f"Lien symbolique interdit : {chemin}")

    try:
        manifeste = json.loads(manifeste_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise CommandError(f"Manifeste illisible : {erreur}") from erreur

    if manifeste.get("format") != FORMAT or manifeste.get("version") != VERSION:
        raise CommandError("Format ou version de sauvegarde non pris en charge.")
    if not isinstance(manifeste.get("objects"), list):
        raise CommandError("La liste des objets du manifeste est invalide.")

    noms = set()
    attendus = set()
    for entree in manifeste["objects"]:
        if not isinstance(entree, dict):
            raise CommandError("Une entrée du manifeste est invalide.")
        nom = entree.get("name")
        if not isinstance(nom, str) or not _nom_valide(nom):
            raise CommandError(f"Nom d’objet invalide dans le manifeste : {nom!r}")
        if nom in noms:
            raise CommandError(f"Objet dupliqué dans le manifeste : {nom}")
        noms.add(nom)

        chemin = _chemin_objet(objets_dir, nom)
        if not chemin.is_file() or chemin.is_symlink():
            raise CommandError(f"Objet sauvegardé introuvable : {nom}")
        taille, somme = _hacher_fichier(chemin)
        if entree.get("size") != taille:
            raise CommandError(f"Taille incorrecte pour l’objet : {nom}")
        if entree.get("sha256") != somme:
            raise CommandError(f"Somme SHA-256 incorrecte pour l’objet : {nom}")
        attendus.add(chemin.relative_to(objets_dir).as_posix())

    presents = set()
    for chemin in objets_dir.rglob("*"):
        if chemin.is_file():
            presents.add(chemin.relative_to(objets_dir).as_posix())

    inattendus = presents - attendus
    if inattendus:
        raise CommandError(
            "Objets absents du manifeste : " + ", ".join(sorted(inattendus))
        )

    return manifeste


def restaurer(stockage, source):
    source = Path(source)
    manifeste = verifier(source)
    objets_dir = source / "objets"
    try:
        existants = [
            entree["name"]
            for entree in manifeste["objects"]
            if stockage.exists(entree["name"])
        ]
    except Exception as erreur:
        raise CommandError(
            f"Impossible de contrôler le stockage cible : {erreur}"
        ) from erreur
    if existants:
        apercu = ", ".join(existants[:3])
        if len(existants) > 3:
            apercu += ", …"
        raise CommandError(f"Refus d’écraser des objets existants : {apercu}")

    ajoutes = []
    try:
        for entree in manifeste["objects"]:
            nom = entree["name"]
            chemin = _chemin_objet(objets_dir, nom)
            with chemin.open("rb") as source_fichier:
                nom_enregistre = stockage.save(nom, File(source_fichier))
            if nom_enregistre != nom:
                stockage.delete(nom_enregistre)
                raise CommandError(
                    f"Le stockage a renommé {nom!r} en {nom_enregistre!r}."
                )
            ajoutes.append(nom)

            with stockage.open(nom, "rb") as fichier:
                taille, somme = _lire_et_hacher(fichier)
            if taille != entree["size"] or somme != entree["sha256"]:
                raise CommandError(f"Contrôle après restauration échoué : {nom}")
    except Exception as erreur:
        echecs = []
        for nom in reversed(ajoutes):
            try:
                stockage.delete(nom)
            except Exception:
                echecs.append(nom)
        if echecs:
            raise CommandError(
                "Restauration échouée et nettoyage incomplet : "
                + ", ".join(echecs)
            ) from erreur
        if isinstance(erreur, CommandError):
            raise
        raise CommandError(f"Restauration échouée : {erreur}") from erreur

    return manifeste


def _lire_et_hacher(fichier):
    somme = hashlib.sha256()
    taille = 0
    while bloc := fichier.read(TAILLE_BLOC):
        somme.update(bloc)
        taille += len(bloc)
    return taille, somme.hexdigest()
