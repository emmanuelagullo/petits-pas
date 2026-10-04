"""Initialisation unique d'une école sur un déploiement serveur persistant."""

from getpass import getpass
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.forms import InitialisationEcoleForm
from comptes.models import AppartenanceEcole, ResponsabiliteEcole
from suivi.models import Ecole


class Command(BaseCommand):
    help = "Crée une première école et un compte personnel de direction sur un serveur vide."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", required=True)
        parser.add_argument("--commune", default="")
        parser.add_argument("--prenom", required=True)
        parser.add_argument("--nom", required=True)
        parser.add_argument("--utilisateur", required=True)

    def handle(self, *args, **options):
        if (settings.MODE_LOCAL or settings.ENVIRONNEMENT_EPHEMERE
                or settings.ENVIRONNEMENT_ATELIER):
            raise CommandError("Cette commande exige un serveur persistant ordinaire.")
        if Ecole.objects.exists() or get_user_model().objects.exists():
            raise CommandError("École ou compte déjà présent : aucune modification.")

        mot_de_passe = getpass("Mot de passe du premier compte : ")
        confirmation = getpass("Confirmer le mot de passe : ")
        if mot_de_passe != confirmation:
            raise CommandError("Les deux mots de passe diffèrent.")
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
            if Ecole.objects.exists() or get_user_model().objects.exists():
                raise CommandError("École ou compte déjà présent : aucune modification.")
            ecole = Ecole.objects.create(
                nom=formulaire.cleaned_data["ecole_nom"],
                commune=formulaire.cleaned_data["commune"].strip(),
            )
            utilisateur = formulaire.save()
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
