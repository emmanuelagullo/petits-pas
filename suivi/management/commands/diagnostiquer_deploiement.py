import os
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import Error as ErreurBase
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
        parser.add_argument(
            "--exiger-persistant-local",
            action="store_true",
            help="Exige PostgreSQL et des médias privés sur un disque persistant.",
        )

    def _afficher_double_facteur(self):
        """État du 2FA. Information et avertissements seulement : ce point ne
        fait jamais échouer le diagnostic d'un profil existant."""
        from carnet.double_facteur import NOMS_RANGS

        nom_du_rang = {rang: nom for nom, rang in NOMS_RANGS.items()}

        if settings.MODE_LOCAL:
            etat = "indisponible (mode local)"
        elif settings.DOUBLE_FACTEUR_DISPONIBLE:
            etat = "disponible"
        elif not settings.DOUBLE_FACTEUR_DEPENDANCES:
            etat = "absent (dépendances de requirements-2fa.txt non installées)"
        else:
            etat = "absent (CARNET_2FA_CLE non renseignée)"
        self.stdout.write(f"- Authentification à deux facteurs : {etat}")
        if not settings.DOUBLE_FACTEUR_DISPONIBLE:
            try:
                modele = apps.get_model("suivi", "PolitiqueDoubleFacteurEcole")
                sans_effet = modele.objects.filter(obligatoire_jusqu_au_rang__gt=0).count()
            except ErreurBase:
                return
            if sans_effet:
                self.stdout.write(self.style.WARNING(
                    f"  {sans_effet} école(s) ont posé une obligation de second facteur "
                    "qui est sans effet tant que la fonction est indisponible."
                ))
            return
        obligatoire = settings.DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG
        desactive = settings.DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG
        if obligatoire:
            self.stdout.write(
                f"  Obligatoire jusqu'au rang {obligatoire} ({nom_du_rang[obligatoire]}), "
                f"délai de grâce {settings.DOUBLE_FACTEUR_DELAI_GRACE_JOURS} jour(s)"
            )
        else:
            self.stdout.write("  Aucune obligation posée par le déployeur (facultatif, les écoles peuvent l'exiger)")
        if desactive <= 5:
            self.stdout.write(f"  Retiré à partir du rang {desactive} ({nom_du_rang[desactive]})")
        self.stdout.write(f"  Clés de chiffrement : {len(settings.DOUBLE_FACTEUR_CLES)}")
        if len(settings.DOUBLE_FACTEUR_CLES) > 1:
            self.stdout.write(self.style.WARNING(
                "  Plusieurs clés : une rotation est en cours. Retirez l'ancienne de "
                "CARNET_2FA_CLE quand plus aucun secret n'en dépend."
            ))
        if settings.PROXYS_DE_CONFIANCE == 0 and not settings.DEBUG:
            self.stdout.write(self.style.WARNING(
                "  Les plafonds de saisie des codes sont par adresse : derrière un "
                "reverse-proxy, voir CARNET_PROXYS_NB dans DEPLOIEMENT.org."
            ))

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
        if settings.EMAIL_DISPONIBLE:
            etat_email = f"actif ({settings.EMAIL_BACKEND})"
        elif settings.EMAIL_CONFIGURATION_EXPLICITE:
            etat_email = "désactivé explicitement"
        else:
            etat_email = "non configuré"
        self.stdout.write(f"- Courriel : {etat_email}")
        if settings.EMAIL_DISPONIBLE and (
            settings.EMAIL_BACKEND.endswith(".smtp.EmailBackend")
            or settings.EMAIL_BACKEND.startswith("anymail.")
        ) and "petits-pas.example" in settings.DEFAULT_FROM_EMAIL:
            # Information, jamais une erreur (voir DEPLOIEMENT.org).
            self.stdout.write(
                self.style.WARNING(
                    "  L'expéditeur est encore l'adresse fictive par défaut "
                    "(petits-pas.example) : les serveurs de réception "
                    "refuseront ou classeront en indésirables les courriels. "
                    "Définir CARNET_EMAIL_EXPEDITEUR avec un domaine réel "
                    "(SPF/DKIM)."
                )
            )
        if settings.ANTIBRUTEFORCE_ACTIF:
            minutes = int(settings.AXES_COOLOFF_TIME.total_seconds() // 60)
            etat_antibruteforce = (
                f"actif ({settings.AXES_FAILURE_LIMIT} échecs, "
                f"blocage de {minutes} min)"
            )
        else:
            etat_antibruteforce = "inactif"
        self.stdout.write(f"- Anti-bruteforce à la connexion : {etat_antibruteforce}")
        if settings.PROXYS_DE_CONFIANCE > 0:
            self.stdout.write(
                "- Adresse IP des clients : lue derrière "
                f"{settings.PROXYS_DE_CONFIANCE} proxy(s) de confiance"
            )
        else:
            self.stdout.write(
                "- Adresse IP des clients : adresse directe (REMOTE_ADDR)"
            )
            if https_force:
                # Information, jamais une erreur : un déploiement existant
                # ne doit pas échouer à cause de ce point (voir DEPLOIEMENT.org).
                self.stdout.write(
                    self.style.WARNING(
                        "  Si l'application est derrière un reverse-proxy, "
                        "tous les clients paraissent avoir la même adresse : "
                        "le blocage après échecs de connexion se réduit à "
                        "l'identifiant seul et le plafond du mot de passe "
                        "oublié devient commun à tous. Voir CARNET_PROXYS_NB "
                        "dans DEPLOIEMENT.org."
                    )
                )

        self._afficher_double_facteur()

        erreurs = []

        if not postgresql:
            erreurs.append("la base n'est pas PostgreSQL")
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
        if not settings.ANTIBRUTEFORCE_ACTIF:
            erreurs.append("l'anti-bruteforce à la connexion est inactif")
        if not settings.EMAIL_CONFIGURATION_EXPLICITE:
            erreurs.append(
                "le courriel n'est ni configuré ni désactivé explicitement"
            )

        erreurs_s3 = list(erreurs)
        if not s3:
            erreurs_s3.append("les médias ne sont pas stockés sur S3")

        erreurs_local = list(erreurs)
        if atelier or ephemere:
            erreurs_local.append("l'environnement n'est pas persistant ordinaire")
        if stockage != "django.core.files.storage.FileSystemStorage":
            erreurs_local.append("le stockage des médias n'est pas local")
        if not os.environ.get("CARNET_MEDIA_ROOT"):
            erreurs_local.append("CARNET_MEDIA_ROOT n'est pas défini explicitement")
        racine = Path(settings.MEDIA_ROOT)
        if not racine.is_absolute():
            erreurs_local.append("CARNET_MEDIA_ROOT n'est pas absolu")
        else:
            racine = racine.resolve()
            code = Path(settings.BASE_DIR).resolve()
            statiques = Path(settings.STATIC_ROOT).resolve()
            if racine == code or code in racine.parents:
                erreurs_local.append("les médias sont dans le répertoire du code")
            if racine == statiques or statiques in racine.parents:
                erreurs_local.append("les médias sont dans les fichiers statiques")
            if not racine.is_dir():
                erreurs_local.append("le répertoire des médias n'existe pas")

        erreurs_atelier = list(erreurs_s3)
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

        if options["exiger_persistant"] and erreurs_s3:
            raise CommandError(
                "Profil persistant invalide : " + "; ".join(erreurs_s3)
            )

        if options["exiger_persistant_local"]:
            if erreurs_local:
                raise CommandError(
                    "Profil persistant local invalide : "
                    + "; ".join(erreurs_local)
                )
            self.stdout.write(self.style.SUCCESS("Profil persistant local valide."))
            return

        if erreurs_s3:
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
