"""Diagnostic et nettoyage ciblé après interruption ; aucun nouvel import."""
import json

from django.core.management.base import BaseCommand, CommandError

from comptes.models import Utilisateur
from suivi.imports_ecole import verifier_serveur
from suivi.reprise_import import verrou_imports, diagnostiquer, nettoyer


class Command(BaseCommand):
    help = "Diagnostique les imports journalisés ; nettoie uniquement un import abandonné explicite."

    def add_arguments(self, parser):
        parser.add_argument('--nettoyer', metavar='UUID', help="Identifiant affiché au diagnostic.")
        parser.add_argument('--operateur', help="Compte technique actif, obligatoire pour nettoyer.")

    def handle(self, *args, **options):
        verifier_serveur()
        with verrou_imports() as racine:
            if options['nettoyer']:
                if not Utilisateur.objects.filter(username=options['operateur'],
                        is_active=True, is_staff=True).exists():
                    raise CommandError("Le nettoyage exige --operateur : compte technique actif.")
                nettoyer(racine, options['nettoyer'])
                self.stdout.write("Médias abandonnés nettoyés ; journal conservé. Relancer la vérification du ZIP initial.")
                return
            for chemin in sorted(racine.glob('*.json')):
                self.stdout.write(json.dumps(diagnostiquer(racine, chemin.stem), ensure_ascii=False))
            self.stdout.write("Importé : ne pas réimporter ; accueil non confirmé : consulter les audits et renvoyer_accueil_import si nécessaire. "
                "Abandonné : nettoyer explicitement puis vérifier à nouveau le ZIP. "
                "Les anciens préfixes sans journal et les temporaires privés exigent un examen manuel.")
