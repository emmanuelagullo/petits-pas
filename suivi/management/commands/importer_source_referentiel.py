from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from suivi.services.import_sources_referentiels import importer_source


class Command(BaseCommand):
    help = "Importe une version au catalogue fourni, sans changer les écoles ni les suivis."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Fichier YAML versionné")
        parser.add_argument("--verifier", action="store_true", help="Valide le fichier et les conflits, sans écriture.")

    def handle(self, *args, **options):
        try:
            contenu = Path(options["fichier"]).read_text(encoding="utf-8")
            version, cree, nombre = importer_source(contenu, verifier_seulement=options["verifier"])
        except (OSError, UnicodeError) as erreur:
            raise CommandError("Impossible de lire le fichier YAML en UTF-8.") from erreur
        except ValidationError as erreur:
            raise CommandError(" ; ".join(erreur.messages)) from erreur
        except IntegrityError as erreur:
            raise CommandError("Un import simultané a été détecté ; relancez la commande pour vérifier le résultat.") from erreur
        if options["verifier"]:
            self.stdout.write(f"Fichier valide : {nombre} compétence(s). Aucune écriture.")
        else:
            etat = "importée" if cree else "déjà présente"
            self.stdout.write(f"{version.source.titre} — version {version.numero} {etat} : {nombre} compétence(s).")
            self.stdout.write(f"Identifiant de version pour les choix annuels : {version.pk}.")
            self.stdout.write("Aucun choix d'école ou de classe, aucune observation modifiés.")
