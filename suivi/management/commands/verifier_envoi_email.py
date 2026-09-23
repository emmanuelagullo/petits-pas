from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un e-mail de test pour vérifier la configuration d'envoi."

    def add_arguments(self, parser):
        parser.add_argument(
            "destinataire",
            help="Adresse à laquelle envoyer le message de vérification.",
        )

    def handle(self, *args, **options):
        destinataire = options["destinataire"]

        self.stdout.write(f"- Backend : {settings.EMAIL_BACKEND}")
        self.stdout.write(f"- Expéditeur : {settings.DEFAULT_FROM_EMAIL}")

        try:
            envoyes = send_mail(
                subject="Petits Pas — vérification de l'envoi d'e-mail",
                message=(
                    "Ce message confirme que l'envoi d'e-mail est "
                    "correctement configuré pour Petits Pas."
                ),
                from_email=None,
                recipient_list=[destinataire],
                fail_silently=False,
            )
        except Exception as erreur:
            raise CommandError(f"Échec de l'envoi : {erreur}") from erreur

        if envoyes != 1:
            raise CommandError(
                "L'envoi n'a signalé aucun message transmis."
            )

        self.stdout.write(
            self.style.SUCCESS(f"Message envoyé à {destinataire}.")
        )
