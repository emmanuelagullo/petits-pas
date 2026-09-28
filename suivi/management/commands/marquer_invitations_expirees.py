from django.core.management.base import BaseCommand
from django.utils import timezone

from comptes.models import Invitation


class Command(BaseCommand):
    help = (
        "Marque EXPIREE en base les invitations en attente dont la date "
        "limite est dépassée (à exécuter périodiquement)."
    )

    def handle(self, *args, **options):
        nombre = Invitation.objects.filter(
            etat=Invitation.EN_ATTENTE, expire_le__lt=timezone.now()
        ).update(etat=Invitation.EXPIREE)
        self.stdout.write(
            self.style.SUCCESS(f"{nombre} invitation(s) marquée(s) expirée(s).")
        )
