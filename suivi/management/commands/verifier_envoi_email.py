import smtplib
import socket
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

# Domaines réservés par la RFC 2606 : ne peuvent jamais recevoir de courriel
# réel. Un expéditeur sur l'un de ces domaines explique à lui seul un envoi
# qui échoue ou qui disparaît sans trace.
DOMAINES_RESERVES = (".example", ".test", ".invalid", ".localhost")

BACKENDS_SANS_ENVOI_REEL = {
    "django.core.mail.backends.console.EmailBackend": (
        "Backend console : le message est seulement affiché ci-dessous "
        "(ou dans les journaux du serveur), rien n'est transmis sur le "
        "réseau. C'est le comportement par défaut en développement "
        "(CARNET_DEBUG=1) tant que CARNET_EMAIL_BACKEND n'est pas défini "
        "explicitement — c'est la cause la plus fréquente d'un « envoi » "
        "jamais reçu en local."
    ),
    "django.core.mail.backends.dummy.EmailBackend": (
        "Backend factice : chaque message est silencieusement ignoré. "
        "C'est le repli automatique hors développement quand ni "
        "CARNET_EMAIL_BACKEND ni CARNET_EMAIL_DESACTIVE=oui n'ont été "
        "définis — `manage.py diagnostiquer_deploiement` doit signaler ce "
        "cas comme une erreur de configuration."
    ),
}


class Command(BaseCommand):
    help = "Envoie un e-mail de test et diagnostique la configuration d'envoi."

    def add_arguments(self, parser):
        parser.add_argument(
            "destinataire",
            help="Adresse à laquelle envoyer le message de vérification.",
        )

    def handle(self, *args, **options):
        destinataire = options["destinataire"]

        if not settings.EMAIL_DISPONIBLE:
            raise CommandError(
                "L'envoi de courriel est désactivé sur cette installation "
                "(CARNET_EMAIL_DESACTIVE=oui)."
            )

        self.stdout.write(f"- Backend : {settings.EMAIL_BACKEND}")

        avertissement_backend = BACKENDS_SANS_ENVOI_REEL.get(settings.EMAIL_BACKEND)
        if avertissement_backend:
            self.stdout.write(self.style.WARNING(avertissement_backend))

        if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
            self.stdout.write(
                f"- Serveur : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
                f"(TLS {'activé' if settings.EMAIL_USE_TLS else 'désactivé'})"
            )
            if not settings.EMAIL_HOST_USER:
                self.stdout.write(
                    self.style.WARNING(
                        "CARNET_EMAIL_UTILISATEUR est vide : la plupart des "
                        "serveurs SMTP exigent une authentification."
                    )
                )

        _, adresse = parseaddr(settings.DEFAULT_FROM_EMAIL)
        self.stdout.write(f"- Expéditeur : {settings.DEFAULT_FROM_EMAIL}")
        domaine = adresse.rsplit("@", 1)[-1] if "@" in adresse else ""
        if any(domaine.endswith(reserve) for reserve in DOMAINES_RESERVES):
            self.stdout.write(
                self.style.WARNING(
                    f"Le domaine expéditeur « {domaine} » est réservé "
                    "(RFC 2606) et n'existe sur aucun serveur de messagerie "
                    "réel : la plupart des relais SMTP le rejettent, et "
                    "ceux qui l'acceptent voient le message classé "
                    "indésirable par le destinataire. Définissez "
                    "CARNET_EMAIL_EXPEDITEUR avec une adresse dont le "
                    "domaine existe réellement — idéalement celui du "
                    "compte SMTP utilisé pour l'envoi."
                )
            )

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
        except smtplib.SMTPAuthenticationError as erreur:
            raise CommandError(
                "Authentification refusée par le serveur SMTP : vérifiez "
                "CARNET_EMAIL_UTILISATEUR et CARNET_EMAIL_MOT_DE_PASSE "
                f"({erreur})."
            ) from erreur
        except smtplib.SMTPSenderRefused as erreur:
            raise CommandError(
                "L'expéditeur a été refusé par le serveur : le domaine de "
                "CARNET_EMAIL_EXPEDITEUR n'est probablement pas autorisé à "
                f"émettre depuis ce compte ({erreur})."
            ) from erreur
        except smtplib.SMTPRecipientsRefused as erreur:
            raise CommandError(
                "Le destinataire a été refusé par le serveur, souvent "
                "parce que l'expéditeur n'est pas jugé légitime — vérifiez "
                f"CARNET_EMAIL_EXPEDITEUR ({erreur})."
            ) from erreur
        except (
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
            ConnectionRefusedError,
            socket.gaierror,
            socket.timeout,
        ) as erreur:
            raise CommandError(
                "Impossible de joindre le serveur SMTP : vérifiez "
                "CARNET_EMAIL_HOTE et CARNET_EMAIL_PORT, et que ce "
                "déploiement autorise les connexions sortantes sur ce port "
                f"({erreur})."
            ) from erreur
        except smtplib.SMTPException as erreur:
            raise CommandError(f"Échec de l'envoi (SMTP) : {erreur}") from erreur
        except Exception as erreur:
            raise CommandError(f"Échec de l'envoi : {erreur}") from erreur

        if envoyes != 1:
            raise CommandError(
                "L'envoi n'a signalé aucun message transmis."
            )

        if avertissement_backend:
            self.stdout.write(
                self.style.WARNING(
                    "Commande terminée sans erreur, mais rappel : ce "
                    "backend n'envoie rien réellement (voir ci-dessus)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Message accepté par le serveur pour {destinataire}."
                )
            )
            self.stdout.write(
                "Ceci confirme l'acceptation par le serveur d'envoi, pas la "
                "livraison en boîte de réception : sans domaine "
                "d'expédition muni de SPF/DKIM, le message peut encore être "
                "classé indésirable ou rejeté silencieusement en aval "
                "(voir AUDIT-AUTHENTIFICATION-INVITATIONS.org, §3.2)."
            )
