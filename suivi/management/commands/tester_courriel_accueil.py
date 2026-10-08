"""Aperçu des vrais messages d'accueil, sans écriture ni jeton d'accès."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.utils import timezone

from comptes.models import AffectationClasse, Invitation, Utilisateur
from suivi.courriels_comptes import composer_accueil
from suivi.models import Classe, Ecole, annee_scolaire_pour

SCENARIOS = {
    "direction": None,
    "direction-import": None,
    "sans-fonction": None,
    "responsable": AffectationClasse.RESPONSABLE,
    "associe": AffectationClasse.ENSEIGNANT_ASSOCIE,
    "contributeur": AffectationClasse.CONTRIBUTEUR,
}


class Command(BaseCommand):
    help = "Envoie un aperçu d’accueil fictif, sans créer de compte, invitation ou droits."

    def add_arguments(self, parser):
        parser.add_argument("destinataire", help="Adresse de réception, même déjà connue de l’application.")
        parser.add_argument("--scenario", choices=SCENARIOS, default="direction")

    def handle(self, *args, **options):
        adresse = options["destinataire"].strip()
        try:
            validate_email(adresse)
        except ValidationError:
            raise CommandError("Adresse électronique invalide.") from None
        if not settings.EMAIL_DISPONIBLE or settings.EMAIL_BACKEND in {
            "django.core.mail.backends.console.EmailBackend",
            "django.core.mail.backends.filebased.EmailBackend",
            "django.core.mail.backends.dummy.EmailBackend",
        }:
            raise CommandError("Courrier désactivé ou sans envoi : aucun message transmis.")

        # Objets uniquement en mémoire : aucune recherche de l'identité du destinataire.
        ecole = Ecole(nom="École fictive — test de courriel", commune="Commune fictive")
        maintenant = timezone.now()
        invitation = Invitation(ecole=ecole, email=adresse, expire_le=maintenant + timedelta(days=7))
        compte = Utilisateur(username="camille-test", first_name="Camille", last_name="Fictive")
        fonctions = []
        fonction = SCENARIOS[options["scenario"]]
        if fonction:
            classe = Classe(ecole=ecole, nom="Les Mésanges fictives",
                            annee_scolaire=annee_scolaire_pour(timezone.localdate()))
            fonctions.append(AffectationClasse(invitation=invitation, classe=classe,
                type=fonction, date_debut=timezone.localdate(),
                date_fin=timezone.localdate() + timedelta(days=30)))
        message = composer_accueil(
            ecole=ecole, destinataire=adresse,
            lien="https://example.invalid/activation-desactivee/",
            compte=compte if options["scenario"] in ("direction", "direction-import") else None,
            invitation=invitation, preattributions=fonctions, mode_test=True,
            apres_import=options["scenario"] == "direction-import",
        )
        try:
            resultat = message.send(fail_silently=False)
        except Exception:
            raise CommandError("Envoi non confirmé. Vérifier le transport des courriels ; aucun compte ni droit créé.") from None
        if resultat != 1:
            raise CommandError("Envoi non confirmé ; aucun compte ni droit créé.")
        self.stdout.write(self.style.SUCCESS(
            "Courriel de test accepté par le transport ; vérifier sa réception et son rendu. "
            "Aucun compte, invitation ou droit créé."
        ))
