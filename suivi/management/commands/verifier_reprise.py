import subprocess

from django.core.management.base import BaseCommand, CommandError

from suivi.reprises import verifier


class Command(BaseCommand):
    help = "Vérifie intégralement un paquet de reprise coordonné."

    def add_arguments(self, parser):
        parser.add_argument("repertoire")

    def handle(self, *args, **options):
        manifeste, dump = verifier(options["repertoire"])
        try:
            subprocess.run(
                ["pg_restore", "--list", str(dump)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as erreur:
            raise CommandError("Commande introuvable : pg_restore") from erreur
        except subprocess.CalledProcessError as erreur:
            raise CommandError("L’archive PostgreSQL est illisible.") from erreur

        self.stdout.write(
            self.style.SUCCESS(
                "Paquet de reprise vérifié : "
                f"mode {manifeste['mode']}, "
                f"{manifeste['media']['objects']} média(s)."
            )
        )
