from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Vérifie l'écriture, la lecture et la suppression d'un média local."

    def handle(self, *args, **options):
        contenu = b"verification du stockage local de Petits Pas\n"
        nom = f"verifications/{uuid4()}.txt"
        nom_enregistre = None
        try:
            nom_enregistre = default_storage.save(nom, ContentFile(contenu))
            with default_storage.open(nom_enregistre, "rb") as fichier:
                if fichier.read() != contenu:
                    raise CommandError("Le contenu relu diffère du contenu écrit.")
            default_storage.delete(nom_enregistre)
            if default_storage.exists(nom_enregistre):
                raise CommandError("Le média existe encore après suppression.")
        except Exception as erreur:
            if nom_enregistre:
                try:
                    default_storage.delete(nom_enregistre)
                except Exception:
                    pass
            if isinstance(erreur, CommandError):
                raise
            raise CommandError(f"Échec du stockage local : {erreur}") from erreur

        self.stdout.write(self.style.SUCCESS("Écriture, lecture et suppression vérifiées."))
