"""Installation du ZIP fictif dans un emplacement d'essai vierge uniquement."""
from io import BytesIO
from pathlib import Path
import shutil
from .paquet_local import preparer_restauration


def installer_ecole_fictive(archive, destination):
    destination = Path(destination)
    if destination.is_symlink() or (destination / "carnet.sqlite3").exists():
        raise ValueError("L'espace existe déjà : aucune école ne sera remplacée.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("L'espace d'essai doit être vide.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = BytesIO(archive) if isinstance(archive, (bytes, bytearray)) else archive
    preparation = preparer_restauration(source, destination.parent, destination.name,
                                       taille_max=64 * 1024**2, fichiers_max=5000)
    try:
        if destination.exists():
            destination.rmdir()
        preparation.etape.rename(destination)
    finally:
        if preparation.etape.exists():
            shutil.rmtree(preparation.etape)
