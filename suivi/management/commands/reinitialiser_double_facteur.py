from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError

from suivi.services.double_facteur import reinitialiser_par_le_deployeur


class Command(BaseCommand):
    help = (
        "Réinitialise le second facteur d'un compte (téléphone perdu), y compris "
        "celui d'une direction. Si l'obligation s'applique encore, la personne "
        "devra se réinscrire dès sa connexion suivante."
    )

    def add_arguments(self, parser):
        parser.add_argument("--utilisateur", required=True)
        parser.add_argument("--operateur", required=True)
        parser.add_argument("--motif", required=True)

    def handle(self, *args, **options):
        Utilisateur = get_user_model()
        try:
            cible = Utilisateur.objects.get(username=options["utilisateur"])
            operateur = Utilisateur.objects.get(username=options["operateur"])
        except Utilisateur.DoesNotExist as erreur:
            raise CommandError("Utilisateur ou opérateur introuvable.") from erreur
        try:
            reinitialiser_par_le_deployeur(
                operateur=operateur, cible=cible, motif=options["motif"])
        except PermissionDenied as erreur:
            raise CommandError("L'opérateur doit être un compte technique actif.") from erreur
        self.stdout.write(self.style.SUCCESS("Second facteur réinitialisé."))
