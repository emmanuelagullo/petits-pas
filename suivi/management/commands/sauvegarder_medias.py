from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from suivi.sauvegardes_medias import sauvegarder


class Command(BaseCommand):
    help = "Sauvegarde tous les médias avec un manifeste SHA-256."

    def add_arguments(self, parser):
        parser.add_argument("destination")

    def handle(self, *args, **options):
        manifeste = sauvegarder(default_storage, options["destination"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Sauvegarde créée : {options['destination']} "
                f"({len(manifeste['objects'])} objet(s))"
            )
        )
