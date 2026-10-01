from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from suivi.models import ChoixApplicationAnnuel
from suivi.services.garde_fous_referentiels import regler_permission_application
from suivi.services.choix_bases_referentiels import verifier_annee


class Command(BaseCommand):
    help = "Consulte ou règle la permission annuelle de changer de référentiel après saisies."

    def add_arguments(self, parser):
        parser.add_argument("--annee", required=True)
        groupe = parser.add_mutually_exclusive_group()
        groupe.add_argument("--ouvrir", action="store_true")
        groupe.add_argument("--fermer", action="store_true")
        parser.add_argument("--revision-attendue", type=int)
        parser.add_argument("--confirmer-ouverture", action="store_true")

    def handle(self, *args, **options):
        try:
            verifier_annee(options["annee"])
            if options["ouvrir"] or options["fermer"]:
                if options["revision_attendue"] is None:
                    raise CommandError("Consultez d'abord la révision, puis précisez --revision-attendue.")
                regle = regler_permission_application(annee=options["annee"], ouverte=options["ouvrir"],
                    revision_attendue=options["revision_attendue"], confirmer=options["confirmer_ouverture"])
            else:
                regle = ChoixApplicationAnnuel.objects.filter(annee_scolaire=options["annee"]).first()
            self.stdout.write(f"{options['annee']} — révision {regle.revision if regle else 0} — changements après saisies : "
                              + ("permis" if regle and regle.changements_apres_saisies else "interdits"))
            self.stdout.write("ATTENTION : permettre ces changements ouvre une possibilité aux écoles. Chaque école puis chaque classe doit aussi l'autoriser. Aucun parcours ne bascule automatiquement.")
        except ValidationError as cause:
            raise CommandError(" ; ".join(cause.messages)) from cause
