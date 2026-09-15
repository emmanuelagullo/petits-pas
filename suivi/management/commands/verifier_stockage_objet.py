from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Vérifie l'écriture, la lecture, l'URL et la suppression d'un média."

    def handle(self, *args, **options):
        contenu = b"verification du stockage objet de Petits Pas\n"
        nom = f"verifications/{uuid4()}.txt"
        nom_enregistre = None

        try:
            nom_enregistre = default_storage.save(nom, ContentFile(contenu))
            with default_storage.open(nom_enregistre, "rb") as fichier:
                if fichier.read() != contenu:
                    raise CommandError("Le contenu relu diffère du contenu écrit.")

            url = default_storage.url(nom_enregistre)
            self.stdout.write(f"- Objet : {nom_enregistre}")
            self.stdout.write(f"- URL temporaire : {url}")
        except CommandError:
            raise
        except Exception as erreur:
            raise CommandError(f"Échec du stockage : {erreur}") from erreur
        finally:
            if nom_enregistre:
                try:
                    default_storage.delete(nom_enregistre)
                except Exception as erreur:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Impossible de supprimer l'objet de vérification : {erreur}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS("Écriture, lecture, URL et suppression vérifiées.")
        )

