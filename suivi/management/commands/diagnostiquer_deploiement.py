from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


CLE_SECRETE_DE_DEVELOPPEMENT = (
    "dev-seulement-a-changer-avant-toute-mise-en-ligne"
)


class Command(BaseCommand):
    help = "Affiche la configuration effective du déploiement sans révéler de secret."

    def add_arguments(self, parser):
        parser.add_argument(
            "--exiger-persistant",
            action="store_true",
            help=(
                "Échoue si PostgreSQL, le stockage S3 ou les principaux "
                "réglages de sécurité du pilote ne sont pas configurés."
            ),
        )
        parser.add_argument(
            "--exiger-atelier",
            action="store_true",
            help=(
                "Exige le profil persistant et la confirmation explicite "
                "d'un atelier à données exclusivement factices."
            ),
        )

    def handle(self, *args, **options):
        moteur = settings.DATABASES["default"]["ENGINE"]
        stockage = settings.STORAGES["default"]["BACKEND"]

        postgresql = "postgresql" in moteur
        s3 = stockage == "storages.backends.s3.S3Storage"
        cle_secrete_configuree = (
            settings.SECRET_KEY != CLE_SECRETE_DE_DEVELOPPEMENT
        )
        hotes_configures = (
            bool(settings.ALLOWED_HOSTS)
            and "*" not in settings.ALLOWED_HOSTS
        )
        origines_csrf_configurees = bool(settings.CSRF_TRUSTED_ORIGINS)
        proxy_https = getattr(
            settings, "SECURE_PROXY_SSL_HEADER", None
        ) == (
            "HTTP_X_FORWARDED_PROTO",
            "https",
        )
        atelier = settings.ENVIRONNEMENT_ATELIER
        ephemere = settings.ENVIRONNEMENT_EPHEMERE
        version = settings.VERSION_APPLICATION

        self.stdout.write("Diagnostic du déploiement")
        self.stdout.write(
            f"- Base de données : {'PostgreSQL' if postgresql else moteur}"
        )
        self.stdout.write(
            f"- Médias : {'stockage objet S3' if s3 else stockage}"
        )
        self.stdout.write(
            f"- Mode debug : {'activé' if settings.DEBUG else 'désactivé'}"
        )
        self.stdout.write(
            "- Clé secrète : "
            + (
                "configurée"
                if cle_secrete_configuree
                else "valeur de développement"
            )
        )
        self.stdout.write(
            "- Hôtes autorisés : "
            + ("configurés" if hotes_configures else "non restreints")
        )
        self.stdout.write(
            "- Origines CSRF HTTPS : "
            + (
                "configurées"
                if origines_csrf_configurees
                else "absentes"
            )
        )
        self.stdout.write(
            "- Proxy HTTPS : "
            + ("configuré" if proxy_https else "non configuré")
        )
        self.stdout.write(
            "- Environnement : "
            + (
                "atelier pédagogique factice"
                if atelier
                else "éphémère" if ephemere else "persistant ordinaire"
            )
        )
        self.stdout.write(
            "- Version affichée : " + (version if version else "absente")
        )

        erreurs = []

        if not postgresql:
            erreurs.append("la base n'est pas PostgreSQL")
        if not s3:
            erreurs.append("les médias ne sont pas stockés sur S3")
        if settings.DEBUG:
            erreurs.append("DEBUG est activé")
        if not cle_secrete_configuree:
            erreurs.append(
                "la clé secrète de développement est utilisée"
            )
        if not hotes_configures:
            erreurs.append("ALLOWED_HOSTS n'est pas restreint")
        if not origines_csrf_configurees:
            erreurs.append(
                "aucune origine CSRF de confiance n'est configurée"
            )
        if not proxy_https:
            erreurs.append("le proxy HTTPS n'est pas configuré")

        erreurs_atelier = list(erreurs)
        if not atelier:
            erreurs_atelier.append(
                "CARNET_ENVIRONNEMENT_ATELIER ne vaut pas oui"
            )
        if ephemere:
            erreurs_atelier.append(
                "CARNET_ENVIRONNEMENT_EPHEMERE vaut aussi oui"
            )
        if not version:
            erreurs_atelier.append("CARNET_VERSION est absent")

        if options["exiger_atelier"] and erreurs_atelier:
            raise CommandError(
                "Profil atelier invalide : " + "; ".join(erreurs_atelier)
            )

        if options["exiger_persistant"] and erreurs:
            raise CommandError(
                "Profil persistant invalide : " + "; ".join(erreurs)
            )

        if erreurs:
            self.stdout.write(
                self.style.WARNING(
                    "Profil de développement ou de démonstration : "
                    "ne pas utiliser avec des données réelles."
                )
            )
        elif atelier and erreurs_atelier:
            self.stdout.write(
                self.style.WARNING(
                    "Profil atelier incomplet : "
                    + "; ".join(erreurs_atelier)
                )
            )
        elif atelier:
            self.stdout.write(
                self.style.SUCCESS(
                    "Profil atelier valide : données réelles interdites."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Profil persistant valide.")
            )
