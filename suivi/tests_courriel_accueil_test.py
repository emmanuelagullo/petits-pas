from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from comptes.models import Utilisateur, Invitation, AffectationClasse
from suivi.models import Ecole


@override_settings(EMAIL_DISPONIBLE=True,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TestCourrielAccueilTests(TestCase):
    def envoyer(self, scenario="direction", adresse="camille@example.test"):
        sortie = StringIO()
        with self.assertNumQueries(0):
            call_command("tester_courriel_accueil", adresse, scenario=scenario, stdout=sortie)
        return sortie.getvalue()

    def test_tous_les_scenarios_sans_ecriture_ni_lecture_de_la_base(self):
        for scenario, attendu in {
            "direction": "Activer la classe", "sans-fonction": "Aucune fonction",
            "responsable": "Responsable de classe", "associe": "Enseignant associé",
            "contributeur": "Contributeur",
        }.items():
            with self.subTest(scenario=scenario):
                sortie = self.envoyer(scenario)
                message = mail.outbox[-1]
                self.assertTrue(message.subject.startswith("[TEST]"))
                self.assertIn(attendu, message.body)
                self.assertIn("Aucun compte, invitation ou droit", message.body)
                self.assertNotIn("activation-desactivee", message.body)
                self.assertNotIn("activation-desactivee", message.alternatives[0].content)
                self.assertIn("lien désactivé", message.alternatives[0].content)
                self.assertNotIn("https://", sortie)
        for modele in (Utilisateur, Invitation, AffectationClasse, Ecole):
            self.assertEqual(modele.objects.count(), 0)

    def test_adresse_deja_connue_acceptee_sans_modifier_le_compte(self):
        compte = Utilisateur.objects.create_user("camille", email="camille@example.test", password="fictif")
        avant = Utilisateur.objects.values().get(pk=compte.pk)
        self.envoyer()
        self.assertEqual(Utilisateur.objects.values().get(pk=compte.pk), avant)
        self.assertEqual(mail.outbox[0].to, [compte.email])
        self.assertFalse(Invitation.objects.exists())

    def test_echec_et_envoi_non_confirme_sans_details_prives(self):
        for resultat in (0, OSError("détail privé à ne pas afficher")):
            options = {"side_effect": resultat} if isinstance(resultat, Exception) else {"return_value": resultat}
            with patch("suivi.courriels_comptes.EmailMultiAlternatives.send", **options):
                with self.assertRaises(CommandError) as erreur:
                    self.envoyer()
                self.assertNotIn("détail privé", str(erreur.exception))
        self.assertFalse(Utilisateur.objects.exists())

    def test_validation_et_courrier_desactive_avant_envoi(self):
        with self.assertRaises(CommandError):
            self.envoyer(adresse="adresse-invalide")
        with override_settings(EMAIL_DISPONIBLE=False), self.assertRaises(CommandError):
            self.envoyer()
        for backend in ("console", "filebased", "dummy"):
            with override_settings(EMAIL_BACKEND=f"django.core.mail.backends.{backend}.EmailBackend"), self.assertRaises(CommandError):
                self.envoyer()
        self.assertEqual(len(mail.outbox), 0)
