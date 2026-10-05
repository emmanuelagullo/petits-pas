from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from comptes.models import AppartenanceEcole, ResponsabiliteEcole
from suivi.audit import journaliser
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
            ecole = Ecole.objects.select_for_update().get(pk=options["ecole"])
            cible = Utilisateur.objects.get(username=options["utilisateur"])
            operateur = Utilisateur.objects.get(username=options["operateur"])
        except (Ecole.DoesNotExist, Utilisateur.DoesNotExist) as erreur:
            raise CommandError("École ou utilisateur introuvable.") from erreur
        if not operateur.is_active or not operateur.is_staff:
            raise CommandError("L'opérateur doit être un compte technique actif.")
        if not cible.is_active or ecole.etat != Ecole.ACTIVE:
            raise CommandError("Le compte cible et l'école doivent être actifs.")
        # Examiner tous les comptes, avec les mêmes dates que les autorisations.
        aujourd_hui = timezone.localdate()
        if ResponsabiliteEcole.objects.a_la_date().filter(
            appartenance__ecole=ecole, appartenance__etat=AppartenanceEcole.ACTIVE,
            appartenance__date_debut__lte=aujourd_hui,
            appartenance__utilisateur__is_active=True, type=ResponsabiliteEcole.DIRECTION,
        ).filter(Q(appartenance__date_fin__isnull=True) | Q(appartenance__date_fin__gte=aujourd_hui)).exists():
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
        from suivi.acces_double_facteur import fermer_sessions_compte, poser_echeance_si_besoin
        from django.conf import settings
        poser_echeance_si_besoin(cible, delai_de_grace=False)
        if settings.DOUBLE_FACTEUR_DISPONIBLE:
            fermer_sessions_compte(cible)
        journaliser(
            operateur,
            "direction.secours",
            responsabilite,
            nouvelles={"motif": options["motif"], "utilisateur_id": cible.pk},
        )
        self.stdout.write(self.style.SUCCESS("Direction de secours attribuée."))
