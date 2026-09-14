import secrets

from django.core.management.base import BaseCommand

from suivi.models import Ecole

MOTS = (
    "cerise soleil tortue nuage crayon panda cabane brindille flocon "
    "lanterne grenade sirop biscuit hibou marelle toupie"
).split()


def phrase():
    return "-".join(secrets.choice(MOTS) for _ in range(3))


class Command(BaseCommand):
    help = "Crée une école et affiche ses deux mots de passe."

    def add_arguments(self, parser):
        parser.add_argument("nom")
        parser.add_argument("--commune", default="")
        parser.add_argument("--mdp-enseignant")
        parser.add_argument("--mdp-direction")

    def handle(self, *args, **options):
        enseignant = options["mdp_enseignant"] or phrase()
        direction = options["mdp_direction"] or phrase()
        ecole = Ecole(nom=options["nom"], commune=options["commune"])
        ecole.definir_mots_de_passe(enseignant, direction)
        ecole.save()
        self.stdout.write(self.style.SUCCESS(f"École créée : {ecole} (id {ecole.pk})"))
        self.stdout.write(f"  mot de passe enseignant : {enseignant}")
        self.stdout.write(f"  mot de passe direction  : {direction}")
        self.stdout.write(
            "Notez-les maintenant, ils ne sont pas stockés en clair."
        )
