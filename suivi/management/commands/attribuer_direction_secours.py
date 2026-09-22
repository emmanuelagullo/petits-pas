from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.models import AppartenanceEcole, ResponsabiliteEcole
from suivi.audit import journaliser
from suivi.autorisations import est_direction
from suivi.models import Ecole


class Command(BaseCommand):
    help = "Rétablit une direction lorsqu'une école n'en possède plus."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", type=int, required=True)
        parser.add_argument("--utilisateur", required=True)
        parser.add_argument("--operateur", required=True)
        parser.add_argument("--motif", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        Utilisateur = get_user_model()
        try:
            ecole = Ecole.objects.get(pk=options["ecole"])
            cible = Utilisateur.objects.get(username=options["utilisateur"])
            operateur = Utilisateur.objects.get(username=options["operateur"])
        except (Ecole.DoesNotExist, Utilisateur.DoesNotExist) as erreur:
            raise CommandError("École ou utilisateur introuvable.") from erreur
        if not operateur.is_active or not operateur.is_staff:
            raise CommandError("L'opérateur doit être un compte technique actif.")
        if est_direction(cible, ecole) or ResponsabiliteEcole.objects.a_la_date().filter(
            appartenance__ecole=ecole,
            appartenance__etat=AppartenanceEcole.ACTIVE,
            type=ResponsabiliteEcole.DIRECTION,
        ).exists():
            raise CommandError("L'école possède déjà une direction active.")
        appartenance = AppartenanceEcole.objects.a_la_date().filter(
            utilisateur=cible, ecole=ecole
        ).first()
        if appartenance is None:
            appartenance = AppartenanceEcole.objects.create(
                utilisateur=cible,
                ecole=ecole,
                attribue_par=operateur,
                motif=options["motif"],
            )
        try:
            responsabilite = ResponsabiliteEcole.objects.create(
                appartenance=appartenance,
                attribue_par=operateur,
                motif=options["motif"],
            )
        except ValidationError as erreur:
            raise CommandError(str(erreur)) from erreur
        journaliser(
            operateur,
            "direction.secours",
            responsabilite,
            nouvelles={"motif": options["motif"], "utilisateur_id": cible.pk},
        )
        self.stdout.write(self.style.SUCCESS("Direction de secours attribuée."))
