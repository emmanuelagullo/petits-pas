import os

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from suivi.sauvegardes_medias import restaurer


class Command(BaseCommand):
    help = "Restaure des médias vérifiés sans écraser d’objet existant."

    def add_arguments(self, parser):
        parser.add_argument("source")

    def handle(self, *args, **options):
        if os.environ.get("CARNET_AUTORISER_RESTAURATION_MEDIAS") != "oui":
            raise CommandError(
                "Définissez CARNET_AUTORISER_RESTAURATION_MEDIAS=oui."
            )

        manifeste = restaurer(default_storage, options["source"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Restauration terminée : {len(manifeste['objects'])} objet(s)"
            )
        )
