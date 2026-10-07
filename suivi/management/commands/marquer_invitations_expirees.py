from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from comptes.models import Invitation
from suivi.services.equipe import terminer_preattributions


class Command(BaseCommand):
    help = (
        "Marque EXPIREE en base les invitations en attente dont la date "
        "limite est dépassée, et termine leurs pré-attributions de fonction "
        "(à exécuter périodiquement)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        invitations = list(
            Invitation.objects.select_for_update().filter(
                etat=Invitation.EN_ATTENTE, expire_le__lt=timezone.now()
            )
        )
        for invitation in invitations:
            invitation.etat = Invitation.EXPIREE
            invitation.save(update_fields=["etat"])
            terminer_preattributions(invitation, motif="Invitation expirée")
        self.stdout.write(
            self.style.SUCCESS(f"{len(invitations)} invitation(s) marquée(s) expirée(s).")
        )
