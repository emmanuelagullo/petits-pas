"""Initialisation unique d'une école sur un déploiement serveur persistant."""

from getpass import getpass
from io import StringIO
import secrets
from urllib.parse import urlsplit

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from suivi.courriels_comptes import composer_accueil
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.forms import InitialisationEcoleForm
from comptes.models import AppartenanceEcole, ResponsabiliteEcole
from suivi.models import Ecole


class Command(BaseCommand):
    help = "Crée une première école et un compte personnel de direction sur un serveur persistant."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", required=True)
        parser.add_argument("--commune", default="")
        parser.add_argument("--prenom", required=True)
        parser.add_argument("--nom", required=True)
        parser.add_argument("--utilisateur", required=True)
        parser.add_argument("--ajouter-ecole", action="store_true",
                            help="Autorise une nouvelle école dans une base déjà initialisée.")
        parser.add_argument("--email", help="Envoie un lien pour choisir le premier mot de passe.")
        parser.add_argument("--url", help="Origine HTTPS du site, nécessaire avec --email.")

    def handle(self, *args, **options):
        if (settings.MODE_LOCAL or settings.ENVIRONNEMENT_EPHEMERE
                or settings.ENVIRONNEMENT_ATELIER):
            raise CommandError("Cette commande exige un serveur persistant ordinaire.")
        if not options["ajouter_ecole"] and (Ecole.objects.exists() or get_user_model().objects.exists()):
            raise CommandError("École ou compte déjà présent : aucune modification.")

        email = (options["email"] or "").strip().casefold()
        if options["email"] is not None and not email:
            raise CommandError("Adresse électronique obligatoire avec --email.")
        if email:
            try:
                validate_email(email)
            except ValidationError:
                raise CommandError("Adresse électronique invalide.") from None
            origine = urlsplit(options["url"] or "")
            if (origine.scheme != "https" or not origine.hostname or origine.username
                    or origine.password or origine.path not in ("", "/")
                    or origine.query or origine.fragment):
                raise CommandError("--url doit être une origine HTTPS sans chemin ni identifiants.")
            if (not settings.EMAIL_DISPONIBLE or settings.EMAIL_BACKEND in (
                    "django.core.mail.backends.console.EmailBackend",
                    "django.core.mail.backends.filebased.EmailBackend",
                    "django.core.mail.backends.dummy.EmailBackend")):
                raise CommandError("Courrier désactivé : aucune modification.")
            if get_user_model().objects.filter(email__iexact=email).exists():
                raise CommandError("Adresse déjà utilisée : aucune modification.")
            # Hash utilisable pour le parcours Mot de passe oublié ; valeur jamais transmise.
            mot_de_passe = confirmation = secrets.token_urlsafe(48)
        else:
            if options["url"]:
                raise CommandError("--url exige --email.")
            mot_de_passe = getpass("Mot de passe du premier compte : ")
            confirmation = getpass("Confirmer le mot de passe : ")
            if mot_de_passe != confirmation:
                raise CommandError("Les deux mots de passe diffèrent.")
        if Ecole.objects.filter(nom__iexact=options["ecole"].strip(),
                                commune__iexact=options["commune"].strip()).exists():
            raise CommandError("École de même nom et commune déjà présente : aucune modification.")
        formulaire = InitialisationEcoleForm({
            "ecole_nom": options["ecole"],
            "commune": options["commune"],
            "first_name": options["prenom"],
            "last_name": options["nom"],
            "username": options["utilisateur"],
            "password1": mot_de_passe,
            "password2": confirmation,
        })
        if not formulaire.is_valid():
            details = "; ".join(
                f"{champ} : {', '.join(erreurs)}"
                for champ, erreurs in formulaire.errors.items()
            )
            raise CommandError(f"Initialisation refusée : {details}")

        with transaction.atomic():
            if not options["ajouter_ecole"] and (Ecole.objects.exists() or get_user_model().objects.exists()):
                raise CommandError("École ou compte déjà présent : aucune modification.")
            ecole = Ecole.objects.create(
                nom=formulaire.cleaned_data["ecole_nom"],
                commune=formulaire.cleaned_data["commune"].strip(),
            )
            utilisateur = formulaire.save(commit=False)
            utilisateur.email = email
            utilisateur.save()
            appartenance = AppartenanceEcole.objects.create(
                utilisateur=utilisateur, ecole=ecole
            )
            ResponsabiliteEcole.objects.create(
                appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION
            )
            call_command(
                "charger_referentiel",
                settings.BASE_DIR / "referentiel" / "trame-cycle1.yaml",
                ecole=ecole.pk,
                stdout=StringIO(),
            )
            from suivi.services.reprise_referentiels import preparer_nouvelle_ecole
            preparer_nouvelle_ecole(ecole)
        self.stdout.write(self.style.SUCCESS(
            f"École créée (id {ecole.pk}) ; compte personnel : {utilisateur.username}."
        ))

        if email:
            lien = options["url"].rstrip("/") + reverse(
                "mot_de_passe_reinitialiser",
                kwargs={"uidb64": urlsafe_base64_encode(force_bytes(utilisateur.pk)),
                        "token": default_token_generator.make_token(utilisateur)},
            )
            try:
                resultat = composer_accueil(
                    ecole=ecole, compte=utilisateur, destinataire=email, lien=lien,
                ).send(fail_silently=False)
                if resultat != 1:
                    raise RuntimeError("envoi non confirmé")
            except Exception:
                raise CommandError(
                    "École et compte créés, mais envoi non confirmé. Ne pas recréer : "
                    "utiliser Mot de passe oublié sur le site, puis vérifier la réception."
                ) from None
            self.stdout.write("Courriel accepté par le backend ; réception à vérifier avec le destinataire.")
