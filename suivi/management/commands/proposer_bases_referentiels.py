from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from suivi.models import ChoixApplicationAnnuel
from suivi.services.choix_bases_referentiels import publier_choix_application, verifier_annee


class Command(BaseCommand):
    help = "Consulte ou publie les bases autorisées et le défaut de l'application pour une année."

    def add_arguments(self, parser):
        parser.add_argument("--annee", required=True)
        parser.add_argument("--autoriser", type=int, nargs="*", default=None, metavar="VERSION_ID")
        parser.add_argument("--defaut", type=int, default=None, metavar="VERSION_ID")
        parser.add_argument("--revision-attendue", type=int, default=None)

    def handle(self, *args, **options):
        try:
            verifier_annee(options["annee"])
            if options["autoriser"] is None:
                if options["defaut"] is not None or options["revision_attendue"] is not None:
                    raise CommandError("Pour publier, précisez --autoriser, --defaut et --revision-attendue.")
                choix = ChoixApplicationAnnuel.objects.filter(annee_scolaire=options["annee"]).first()
                if choix is None or not choix.configure:
                    self.stdout.write("Choix non publiés ; seule la base initiale locale reste proposée aux écoles reprises. Révision : 0.")
                    return
            else:
                if options["revision_attendue"] is None:
                    raise CommandError("Précisez --revision-attendue après consultation des choix.")
                choix = publier_choix_application(annee=options["annee"], versions_ids=options["autoriser"],
                    proposee_id=options["defaut"], revision_attendue=options["revision_attendue"])
            self.stdout.write(f"{choix.annee_scolaire} — révision {choix.revision} ; défaut : {choix.version_proposee_id or 'aucun'}")
            for version in choix.versions_autorisees.select_related("source").order_by("pk"):
                self.stdout.write(f"  #{version.pk} — {version.source.titre} — version {version.numero}")
            self.stdout.write("Les bases déjà utilisées par les classes ne sont pas changées.")
        except ValidationError as erreur:
            raise CommandError(" ; ".join(erreur.messages)) from erreur
        except IntegrityError as erreur:
            raise CommandError("Un choix simultané a été détecté ; consultez les choix avant de recommencer.") from erreur
