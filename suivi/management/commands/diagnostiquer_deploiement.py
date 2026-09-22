from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import Resolver404, resolve


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
        https_force = bool(
            settings.SECURE_SSL_REDIRECT
            and settings.SESSION_COOKIE_SECURE
            and settings.CSRF_COOKIE_SECURE
        )
        atelier = settings.ENVIRONNEMENT_ATELIER
        ephemere = settings.ENVIRONNEMENT_EPHEMERE
        version = settings.VERSION_APPLICATION
        modele_ecole = apps.get_model("suivi", "Ecole")
        champs_ecole = {champ.name for champ in modele_ecole._meta.get_fields()}
        acces_historiques_absents = not (
            {"mdp_enseignant", "mdp_direction"} & champs_ecole
            or hasattr(modele_ecole, "verifier")
        )
        identites_individuelles = settings.AUTH_USER_MODEL == "comptes.Utilisateur"
        try:
            resolve("/admin/")
        except Resolver404:
            administration_web_fermee = True
        else:
            administration_web_fermee = False

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
            "- HTTPS et cookies sécurisés : "
            + ("forcés" if https_force else "non forcés")
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
        self.stdout.write(
            "- Identités individuelles : "
            + ("configurées" if identites_individuelles else "absentes")
        )
        self.stdout.write(
            "- Accès partagés persistants : "
            + ("absents" if acces_historiques_absents else "encore présents")
        )
        self.stdout.write(
            "- Administration Django sur le Web : "
            + ("fermée" if administration_web_fermee else "exposée")
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
        if not https_force:
            erreurs.append("HTTPS et les cookies sécurisés ne sont pas forcés")
        if not identites_individuelles:
            erreurs.append("le modèle d'identité individuelle n'est pas configuré")
        if not acces_historiques_absents:
            erreurs.append("les accès partagés historiques sont encore présents")
        if not administration_web_fermee:
            erreurs.append("l'administration Django est exposée sur le Web")

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
