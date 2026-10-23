"""Publication volontaire de la structure, sans changer les classes existantes."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from suivi.models import ChoixApplicationAnnuel
from suivi.services.import_sources_referentiels import importer_source
from suivi.services.choix_bases_referentiels import publier_choix_application


class Command(BaseCommand):
    help = "Autorise la structure sans compétences pour une année, sans changer le défaut ni les classes."

    def add_arguments(self, parser):
        parser.add_argument("--annee", required=True)
        parser.add_argument("--creer-catalogue", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        version, _, _ = importer_source((settings.BASE_DIR / "referentiel/structure-cycle1.yaml").read_text())
        annee = options["annee"]
        politique = ChoixApplicationAnnuel.objects.select_for_update().filter(annee_scolaire=annee).first()
        if not (politique and politique.configure) and not options["creer_catalogue"]:
            raise CommandError("Publiez d’abord le catalogue annuel, ou utilisez --creer-catalogue pour créer un catalogue limité à cette structure.")
        ids = set(politique.versions_autorisees.values_list("pk", flat=True)) if politique and politique.configure else set()
        defaut = politique.version_proposee_id if politique and politique.configure else version.pk
        if version.pk not in ids:
            publier_choix_application(annee=annee, versions_ids=sorted(ids | {version.pk}),
                proposee_id=defaut, revision_attendue=politique.revision if politique else 0)
        self.stdout.write("Structure sans compétences disponible ; propositions d’école et classes inchangées.")
