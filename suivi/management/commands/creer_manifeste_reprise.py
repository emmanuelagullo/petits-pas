import os

from django.core.management.base import BaseCommand, CommandError

from suivi.reprises import creer_manifeste


class Command(BaseCommand):
    help = "Crée le manifeste global d’un paquet de reprise coordonné."

    def add_arguments(self, parser):
        parser.add_argument("repertoire")
        parser.add_argument("--mode", required=True)
        parser.add_argument("--started-at", required=True)
        parser.add_argument("--database-completed-at", required=True)
        parser.add_argument("--media-completed-at", required=True)
        parser.add_argument("--completed-at", required=True)

    def handle(self, *args, **options):
        if (
            options["mode"] == "writes-suspended"
            and os.environ.get("CARNET_ECRITURES_SUSPENDUES") != "oui"
        ):
            raise CommandError(
                "Définissez CARNET_ECRITURES_SUSPENDUES=oui."
            )
        manifeste = creer_manifeste(
            options["repertoire"],
            options["mode"],
            options["started_at"],
            options["database_completed_at"],
            options["media_completed_at"],
            options["completed_at"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Manifeste de reprise créé en mode {manifeste['mode']}."
            )
        )
