from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from suivi.models import Trace


class Command(BaseCommand):
    help = "Vérifie que les médias référencés par la base restaurée existent."

    def handle(self, *args, **options):
        references = list(
            Trace.objects.exclude(photo="")
            .exclude(photo__isnull=True)
            .values_list("photo", flat=True)
        )
        manquants = []
        for nom in references:
            try:
                existe = default_storage.exists(nom)
            except Exception as erreur:
                raise CommandError(
                    f"Impossible de contrôler le média {nom!r} : {erreur}"
                ) from erreur
            if not existe:
                manquants.append(nom)

        if manquants:
            apercu = ", ".join(repr(nom) for nom in manquants[:3])
            if len(manquants) > 3:
                apercu += ", …"
            raise CommandError(
                f"{len(manquants)} média(s) référencé(s) sont absents : {apercu}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cohérence vérifiée : {len(references)} média(s) référencé(s)."
            )
        )
