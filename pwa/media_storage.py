"""Suivre les écritures des médias dans le seul profil navigateur."""
from django.core.files.storage import FileSystemStorage

changed = set()


class LocalMediaStorage(FileSystemStorage):
    def _open(self, name, mode="rb"):
        if any(flag in mode for flag in "wa+"):
            changed.add(name)
        return super()._open(name, mode)

    def _save(self, name, content):
        # Retenir aussi une écriture partielle qui lève une exception.
        changed.add(name)
        saved = super()._save(name, content)
        changed.add(saved)
        return saved

    def delete(self, name):
        changed.add(name)
        return super().delete(name)
