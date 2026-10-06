"""Fichiers OPFS synchrones : blocs bornés, aucun ZIP complet dans Python."""
import io
import json
from pathlib import Path


class OpfsFile(io.RawIOBase):
    def __init__(self, key, name="transfert.zip", start=0, length=None):
        from js import pwaIO
        self.api = pwaIO
        self.key, self.name, self.start, self.length = key, name, start, length
        self.position = 0
        self.max_read = 64 * 1024**2

    def readable(self):
        return True

    def writable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self.position

    def seek(self, offset, whence=0):
        self._checkClosed()
        size = self.length if self.length is not None else self.api.size(self.key) - self.start
        position = offset + (self.position if whence == 1 else size if whence == 2 else 0)
        if position < 0 or whence not in (0, 1, 2):
            raise ValueError("Position de fichier invalide")
        self.position = position
        return position

    def readinto(self, buffer):
        self._checkClosed()
        size = self.length if self.length is not None else self.api.size(self.key) - self.start
        maximum = max(0, min(len(buffer), size - self.position))
        with memoryview(buffer)[:maximum] as block:
            count = self.api.read(self.key, block, self.start + self.position)
        self.position += count
        return count

    def read(self, size=-1):
        self._checkClosed()
        if size < 0:
            # ZipFile lit normalement par blocs ; interdire une matérialisation
            # accidentelle d'une archive entière par un nouveau parcours.
            remaining = (self.length if self.length is not None else self.api.size(self.key) - self.start) - self.position
            if remaining > self.max_read:
                raise ValueError("Lecture complète d'un gros transfert refusée")
            size = max(0, remaining)
        if size > self.max_read:
            raise ValueError("Bloc de transfert trop volumineux")
        buffer = bytearray(size)
        count = self.readinto(buffer)
        return bytes(memoryview(buffer)[:count])

    def write(self, buffer):
        self._checkClosed()
        count = self.api.write(self.key, buffer, self.start + self.position)
        self.position += count
        return count

    def flush(self):
        if not self.closed:
            self.api.flush(self.key)


from django.core.files.uploadhandler import FileUploadHandler
from django.core.files.uploadedfile import UploadedFile


class OpfsUploadHandler(FileUploadHandler):
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        from js import pwaIO
        self.file = OpfsFile("upload", self.file_name, start=pwaIO.size("upload"))

    def receive_data_chunk(self, raw_data, start):
        self.file.write(raw_data)
        return None

    def upload_interrupted(self):
        if hasattr(self, "file"):
            self.file.close()

    def file_complete(self, file_size):
        self.file.length = file_size
        self.file.seek(0)
        return UploadedFile(self.file, self.file_name, self.content_type, file_size, self.charset)


JOB = None


def commencer(request, mode):
    global JOB
    from django.db.migrations.loader import MigrationLoader
    from suivi.paquet_local import iterer_restauration, preparation_en_attente, restauration_en_attente
    from suivi import apercu_local
    if JOB or preparation_en_attente() or restauration_en_attente() or apercu_local.preparation():
        raise ValueError("Terminez ou annulez la préparation en cours.")
    source = request.FILES.get("archive")
    if source is None:
        raise ValueError("Choisissez un fichier ZIP Petits Pas.")
    source.file.max_read = 2 * 1024**2
    def ouvrir(path):
        return OpfsFile("media", str(path)) if "/media/" in str(path) else path.open("xb")
    from .limits import ZIP_BYTES, FILES
    work = iterer_restauration(source, Path("/"), "data" if mode == "restaurer" else "apercu-zip",
        taille_max=ZIP_BYTES, fichiers_max=FILES, migrations_connues=MigrationLoader(None).disk_migrations,
        ouvrir_destination=ouvrir)
    JOB = {"work": work, "request": request, "mode": mode, "source": source}


def etape():
    global JOB
    from django.contrib import messages
    from suivi import apercu_local, paquet_local
    try:
        step = next(JOB["work"])
        from .limits import MEDIA_FILE_BYTES, DATABASE_BYTES
        if step["phase"] == "ouvrir" and step["taille"] > (MEDIA_FILE_BYTES if step["media"] else DATABASE_BYTES):
            JOB["work"].close()
            raise ValueError("Un fichier dépasse 64 Mio : préparation refusée.")
        return json.dumps(step)
    except StopIteration as result:
        if JOB["mode"] == "restaurer":
            paquet_local.retenir_preparation(result.value)
            messages.success(JOB["request"], "Sauvegarde vérifiée. Vérifiez les détails avant de confirmer.")
        else:
            apercu_local.retenir(result.value)
    except Exception as error:
        messages.error(JOB["request"], f"Sauvegarde refusée : {error}")
    JOB = None
    return json.dumps({"phase": "termine"})


def annuler():
    global JOB
    if JOB:
        JOB["work"].close()
        JOB = None
