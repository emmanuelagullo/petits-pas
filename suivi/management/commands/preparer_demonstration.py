"""Scénario commun à la démonstration en ligne et au ZIP fictif."""
from io import StringIO

import yaml
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from suivi.configuration_demo import charger_configuration_demo
from suivi.models import Ecole, SourceReferentiel


class Command(BaseCommand):
    help = "Prépare l'école fictive publique dans une base vide."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.ENVIRONNEMENT_EPHEMERE or Ecole.objects.exists() or get_user_model().objects.exists():
            raise CommandError("Cette préparation exige une base de démonstration vide et éphémère.")
        configuration = charger_configuration_demo(settings.BASE_DIR / "site/data/demonstration.yaml")
        identifiants = configuration["identifiants"]
        call_command("creer_ecole", configuration["ecole"], commune="Bordeaux",
            utilisateur_enseignant=identifiants["enseignant"]["utilisateur"],
            mdp_enseignant=identifiants["enseignant"]["mot_de_passe"],
            utilisateur_direction=identifiants["direction"]["utilisateur"],
            mdp_direction=identifiants["direction"]["mot_de_passe"], stdout=StringIO())
        trame = settings.BASE_DIR / "referentiel/trame-cycle1.yaml"
        call_command("charger_referentiel", trame, stdout=StringIO())
        call_command("jeu_demo_large", stdout=StringIO())
        call_command("jeu_demo_equipe", mot_de_passe=identifiants["enseignant"]["mot_de_passe"],
            confirmer_donnees_fictives=True, stdout=StringIO())
        contenu = yaml.safe_load(trame.read_text(encoding="utf-8"))
        SourceReferentiel.objects.filter(
            ecole=Ecole.objects.get(), versions__contenu__origine="etat_initial_repris",
        ).update(licence=contenu["source"]["licence"],
                 provenance="Trame de démarrage Petits Pas et ajouts fictifs de la démonstration.")
        self.stdout.write("École fictive commune préparée.")
