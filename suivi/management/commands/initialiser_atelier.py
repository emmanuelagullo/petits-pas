import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from suivi.models import Ecole


NOM_ECOLE = "École fictive Petits Pas"
COMMUNE = "Commune fictive"
NOM_CLASSE = "PS-MS-GS de Nadia"


class Command(BaseCommand):
    help = (
        "Initialise une fois l'atelier pédagogique avec un jeu de données "
        "explicitement fictif."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.ENVIRONNEMENT_ATELIER:
            raise CommandError(
                "Refus : CARNET_ENVIRONNEMENT_ATELIER doit valoir oui."
            )
        if settings.ENVIRONNEMENT_EPHEMERE:
            raise CommandError(
                "Refus : l'atelier persistant ne peut pas être éphémère."
            )

        ecoles = Ecole.objects.all()
        if ecoles.exists():
            ecole = ecoles.filter(nom=NOM_ECOLE).first()
            atelier_complet = (
                ecoles.count() == 1
                and ecole is not None
                and ecole.domaines.exists()
                and ecole.classes.filter(nom=NOM_CLASSE).exists()
            )
            if atelier_complet:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Atelier déjà initialisé ; aucune donnée modifiée."
                    )
                )
                return
            raise CommandError(
                "La base n'est ni vide ni un atelier déjà initialisé. "
                "Aucune donnée n'a été modifiée."
            )

        enseignant = os.environ.get("CARNET_ATELIER_MDP_ENSEIGNANT", "")
        direction = os.environ.get("CARNET_ATELIER_MDP_DIRECTION", "")
        if not enseignant or not direction:
            raise CommandError(
                "CARNET_ATELIER_MDP_ENSEIGNANT et "
                "CARNET_ATELIER_MDP_DIRECTION sont obligatoires lors de "
                "la première initialisation."
            )

        ecole = Ecole(nom=NOM_ECOLE, commune=COMMUNE)
        ecole.definir_mots_de_passe(enseignant, direction)
        ecole.save()

        call_command(
            "charger_referentiel",
            settings.BASE_DIR / "referentiel" / "trame-cycle1.yaml",
            ecole=ecole.pk,
            stdout=self.stdout,
        )
        call_command("jeu_demo", stdout=self.stdout)

        self.stdout.write(
            self.style.SUCCESS(
                "Atelier initialisé avec des personnes et observations "
                "entièrement fictives."
            )
        )
