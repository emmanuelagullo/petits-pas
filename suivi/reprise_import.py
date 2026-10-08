"""Journal privé durable et récupération prudente des médias d'import."""
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from django.apps import apps
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import CommandError
from django.db import connections, models

from .models import EvenementAudit


@contextmanager
def verrou_imports():
    # Verrou système libéré même après SIGKILL ; jamais supprimer ce fichier.
    try:
        import fcntl
    except ImportError:
        raise CommandError("L'import serveur journalisé exige un système Unix avec flock.") from None
    if connections['default'].in_atomic_block:
        raise CommandError("L'import et sa récupération doivent être hors transaction englobante.")
    if not isinstance(default_storage, FileSystemStorage):
        raise CommandError("La récupération exige des médias sur disque local.")
    racine = Path(default_storage.path('imports'))
    racine.mkdir(parents=True, exist_ok=True)
    if racine.is_symlink():
        raise CommandError("Répertoire imports symbolique refusé.")
    fd = os.open(racine / '.verrou', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as fichier:
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CommandError("Un import ou une récupération est déjà en cours.") from None
        try:
            yield racine
        finally:
            fcntl.flock(fichier, fcntl.LOCK_UN)


def journaliser(racine, identifiant, **valeurs):
    cible = racine / (identifiant + '.json')
    provisoire = racine / (identifiant + '.tmp')
    fd = os.open(provisoire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fichier:
        json.dump(dict(version=1, identifiant=identifiant, **valeurs), fichier)
        fichier.flush()
        os.fsync(fichier.fileno())
    os.replace(provisoire, cible)
    fd = os.open(racine, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def contient(valeur, prefixe):
    if isinstance(valeur, str):
        return prefixe in valeur
    if isinstance(valeur, dict):
        return any(contient(k, prefixe) or contient(v, prefixe) for k, v in valeur.items())
    if isinstance(valeur, list):
        return any(contient(v, prefixe) for v in valeur)
    return False


def references(prefixe):
    # Inclure toutes les tables installées, même les JSON ajoutés ultérieurement.
    for model in apps.get_models():
        for champ in model._meta.concrete_fields:
            if isinstance(champ, (models.FileField, models.JSONField)):
                for valeur in model._base_manager.values_list(champ.attname, flat=True).iterator(chunk_size=200):
                    if contient(valeur, prefixe):
                        return True
    return False


def diagnostiquer(racine, identifiant):
    if not re.fullmatch('[0-9a-f]{32}', identifiant):
        raise CommandError("Identifiant d'import invalide.")
    fichier = racine / (identifiant + '.json')
    if not fichier.exists() or fichier.is_symlink() or fichier.stat().st_size > 4096:
        raise CommandError("Journal non conforme ; examen manuel nécessaire.")
    try:
        journal = json.loads(fichier.read_text(encoding='utf-8'))
        if journal['version'] != 1 or journal['identifiant'] != identifiant:
            raise ValueError()
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise CommandError("Journal non conforme ; examen manuel nécessaire.") from None
    prefixe = f'imports/{identifiant}/'
    audit = EvenementAudit.objects.filter(action='ecole.import_zip',
        nouvelles_valeurs__medias_prefixe=prefixe).first()
    if audit:
        direction = audit.nouvelles_valeurs.get('direction_id')
        envoye = EvenementAudit.objects.filter(ecole_id=audit.ecole_id,
            action='ecole.import_accueil_envoye', nouvelles_valeurs__direction_id=direction).exists()
        return dict(identifiant=identifiant, etat='importe', ecole_id=audit.ecole_id,
                    accueil='envoi_audite' if envoye else 'non_confirme', nettoyable=False)
    protege = references(prefixe)
    destination = racine / identifiant
    symbolique = destination.is_symlink() or (destination.exists() and not destination.is_dir()) or (destination.exists() and any(
        p.is_symlink() for p in destination.rglob('*')))
    etat = 'references_sans_audit' if protege else 'abandonne'
    if not protege and not destination.exists() and journal.get('etat') == 'nettoye':
        etat = 'nettoye'
    return dict(identifiant=identifiant, etat=etat,
                nettoyable=not protege and not symbolique)


def nettoyer(racine, identifiant):
    bilan = diagnostiquer(racine, identifiant)
    if not bilan['nettoyable']:
        raise CommandError("Nettoyage refusé : import validé, référence ou lien symbolique.")
    destination = racine / identifiant
    if destination.exists():
        shutil.rmtree(destination)
    journaliser(racine, identifiant, etat='nettoye')
    return bilan
