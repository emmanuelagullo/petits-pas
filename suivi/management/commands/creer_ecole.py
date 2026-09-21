import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from suivi.models import Ecole

MOTS = (
    "cerise soleil tortue nuage crayon panda cabane brindille flocon "
    "lanterne grenade sirop biscuit hibou marelle toupie"
).split()


def phrase():
    return "-".join(secrets.choice(MOTS) for _ in range(3))


class Command(BaseCommand):
    help = "Crée une école et ses deux comptes techniques initiaux."

    def add_arguments(self, parser):
        parser.add_argument("nom")
        parser.add_argument("--commune", default="")
        parser.add_argument("--utilisateur-enseignant")
        parser.add_argument("--utilisateur-direction")
        parser.add_argument("--mdp-enseignant")
        parser.add_argument("--mdp-direction")

    @transaction.atomic
    def handle(self, *args, **options):
        enseignant = options["mdp_enseignant"] or phrase()
        direction = options["mdp_direction"] or phrase()
        suffixe = slugify(options["nom"]) or "ecole"
        utilisateur_enseignant = (
            options["utilisateur_enseignant"] or f"enseignant-{suffixe}"
        )
        utilisateur_direction = (
            options["utilisateur_direction"] or f"direction-{suffixe}"
        )
        ecole = Ecole.objects.create(nom=options["nom"], commune=options["commune"])
        Utilisateur = get_user_model()
        Utilisateur.objects.create_user(
            username=utilisateur_enseignant,
            password=enseignant,
            ecole=ecole,
            profil_transition=Utilisateur.ENSEIGNANT,
        )
        Utilisateur.objects.create_user(
            username=utilisateur_direction,
            password=direction,
            ecole=ecole,
            profil_transition=Utilisateur.DIRECTION,
        )
        self.stdout.write(self.style.SUCCESS(f"École créée : {ecole} (id {ecole.pk})"))
        self.stdout.write(f"  compte enseignant : {utilisateur_enseignant}")
        self.stdout.write(f"  mot de passe      : {enseignant}")
        self.stdout.write(f"  compte direction  : {utilisateur_direction}")
        self.stdout.write(f"  mot de passe      : {direction}")
        self.stdout.write(
            "Notez-les maintenant, ils ne sont pas stockés en clair."
        )
