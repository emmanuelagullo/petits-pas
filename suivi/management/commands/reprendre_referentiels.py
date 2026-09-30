from django.core.management.base import BaseCommand, CommandError

from suivi.models import Ecole
from suivi.services.reprise_referentiels import reprendre


class Command(BaseCommand):
    help = "Reprend l'état initial des référentiels ; exclusivement sur une copie restaurée pour ce jalon."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", type=int, required=True)
        parser.add_argument("--appliquer-sur-copie", action="store_true",
                            help="Confirmer que la base est une copie de travail sauvegardée.")

    def handle(self, *args, **options):
        if not options["appliquer_sur_copie"]:
            raise CommandError("Exécuter d'abord diagnostiquer_referentiels ; la reprise exige --appliquer-sur-copie.")
        try:
            cree = reprendre(options["ecole"])
        except Ecole.DoesNotExist:
            raise CommandError("École introuvable.")
        self.stdout.write("État initial repris ; états annuels inconnus conservés explicitement."
                          if cree else "État initial déjà repris ; aucune modification.")
