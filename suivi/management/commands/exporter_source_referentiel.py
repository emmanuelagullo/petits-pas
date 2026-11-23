from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from suivi.models import VersionReferentiel
from suivi.services.paquets_referentiels import exporter_paquet


class Command(BaseCommand):
    help = "Exporte une édition publique du référentiel et ses illustrations fournies."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("version")
        parser.add_argument("fichier", help="Nouveau fichier ZIP")

    def handle(self, *args, **options):
        try:
            version = VersionReferentiel.objects.get(source__identifiant=options["source"],
                source__ecole__isnull=True, numero=options["version"])
            donnees = exporter_paquet(version)
            with Path(options["fichier"]).open("xb") as fichier:
                fichier.write(donnees)
        except VersionReferentiel.DoesNotExist as erreur:
            raise CommandError("Cette édition publique est introuvable.") from erreur
        except ValidationError as erreur:
            raise CommandError(" ; ".join(erreur.messages)) from erreur
        except OSError as erreur:
            raise CommandError(f"Impossible d’écrire le nouveau paquet : {erreur}.") from erreur
