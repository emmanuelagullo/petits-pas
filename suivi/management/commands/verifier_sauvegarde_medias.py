from django.core.management.base import BaseCommand

from suivi.sauvegardes_medias import verifier


class Command(BaseCommand):
    help = "Vérifie le manifeste, les tailles et les SHA-256 des médias."

    def add_arguments(self, parser):
        parser.add_argument("source")

    def handle(self, *args, **options):
        manifeste = verifier(options["source"])
        self.stdout.write(
            self.style.SUCCESS(
                "Sauvegarde vérifiée : "
                f"{len(manifeste['objects'])} objet(s)"
            )
        )
