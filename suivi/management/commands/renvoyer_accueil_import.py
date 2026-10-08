"""Reprendre uniquement le courriel d'accueil après un import déjà validé."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from comptes.models import Utilisateur
from suivi.accueil_import import envoyer_accueil_import
from suivi.models import Ecole


class Command(BaseCommand):
    help = "Renvoie l'accueil à la direction créée lors d'un import, sans recréer de données ni modifier son mot de passe."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', type=int, required=True)
        parser.add_argument('--direction', required=True)
        parser.add_argument('--operateur', required=True)
        parser.add_argument('--url', required=True)

    def handle(self, *args, **options):
        try:
            ecole = Ecole.objects.get(pk=options['ecole'])
            direction = Utilisateur.objects.get(username=options['direction'])
            operateur = Utilisateur.objects.get(username=options['operateur'])
            envoyer_accueil_import(ecole=ecole, direction=direction,
                operateur=operateur, url=options['url'])
        except (Ecole.DoesNotExist, Utilisateur.DoesNotExist):
            raise CommandError("École ou compte introuvable.") from None
        except ValidationError as erreur:
            raise CommandError('; '.join(erreur.messages)) from None
        self.stdout.write("Courriel accepté par le backend ; réception à vérifier avec le destinataire.")
