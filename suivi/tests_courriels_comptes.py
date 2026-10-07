"""Accueils publics : uniquement des comptes et écoles fictifs."""
from datetime import timedelta
from html import unescape
from pathlib import Path
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import AffectationClasse, Invitation
from suivi.autorisations import ACCEDER_APPLICATION, autorise
from suivi.courriels_comptes import GUIDE, PARCOURS, composer_accueil
from suivi.models import EvenementAudit
from suivi.services.equipe import accepter_invitation, envoyer_email_invitation
from suivi.tests_preattributions import BasePreattributions, ADRESSE, MOT_DE_PASSE


@override_settings(EMAIL_DISPONIBLE=True,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   VERSION_APPLICATION="test.2026")
class CourrielsComptesTests(BasePreattributions):
    def message(self, invitation):
        return composer_accueil(ecole=self.ecole, invitation=invitation,
            destinataire=invitation.email, lien="https://ecole.example.test/invitation/fictive/")

    def test_sans_fonction_et_formats_coherents(self):
        invitation, _, _ = self.inviter_avec_fonction()
        invitation.affectations_classes.all().delete()
        message = self.message(invitation)
        self.assertIn("Aucune fonction", message.body)
        self.assertIn("cette appartenance seule n’ouvre pas", message.body)
        self.assertIn("test.2026", message.body)
        self.assertIn("plus récente", message.body)
        self.assertIn("Accepter l’invitation", message.body)
        html = unescape(re.sub("<[^>]*>", " ", message.alternatives[0].content))
        for phrase in ("Aucune fonction", "Créer mon compte et rejoindre l’école",
                       "Accepter l’invitation", "test.2026", GUIDE + PARCOURS["invitation"]):
            self.assertIn(phrase, html)

    def test_fonctions_dates_annees_et_premiers_resultats(self):
        for fonction in (AffectationClasse.RESPONSABLE,
                         AffectationClasse.ENSEIGNANT_ASSOCIE,
                         AffectationClasse.CONTRIBUTEUR):
            with self.subTest(fonction=fonction):
                invitation, _, pre = self.inviter_avec_fonction(
                    adresse=f"invite-{fonction}@example.test", type=fonction)
                pre[0].date_fin = timezone.localdate() + timedelta(days=10)
                pre[0].save()
                message = self.message(invitation)
                self.assertIn(pre[0].get_type_display(), message.body)
                self.assertIn(self.classe.libelle_avec_annee, message.body)
                self.assertIn(pre[0].date_fin.strftime("%d/%m/%Y"), message.body)
                self.assertIn("Ajouter la trace", message.body)
                self.assertIn("droits actuels", message.body)

    def test_liens_documentaires_correspondent_aux_sources(self):
        for chemin in PARCOURS.values():
            source = Path(__file__).resolve().parent.parent / "site/content/guide" / (chemin.rstrip("/") + ".md")
            self.assertTrue(source.is_file())
        message = composer_accueil(ecole=self.ecole, compte=self.direction,
            destinataire=self.direction.email, lien="https://ecole.example.test/choix/fictif/")
        self.assertIn(GUIDE + PARCOURS["direction"], message.body)
        self.assertIn("ne donnent pas automatiquement", message.body)
        self.assertIn("facultatif", message.body)
        self.assertIn("attribuez-vous explicitement", message.body)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")

    def test_compte_existant_et_modification_apres_envoi(self):
        invitation, jeton, pre = self.inviter_avec_fonction(type=AffectationClasse.RESPONSABLE)
        ancien_mail = self.message(invitation).body
        pre[0].type = AffectationClasse.CONTRIBUTEUR
        pre[0].save()
        compte = get_user_model().objects.create_user("invitee", email=ADRESSE, password=MOT_DE_PASSE)
        nombre = get_user_model().objects.count()
        reponse = self.client.post(reverse("accepter_invitation", args=[invitation.selecteur, jeton]),
            {"nom_utilisateur": compte.username, "mot_de_passe": MOT_DE_PASSE})
        self.assertContains(reponse, "Contributeur")
        self.assertEqual(get_user_model().objects.count(), nombre)
        self.assertIn("Responsable de classe", ancien_mail)
        pre[0].refresh_from_db()
        self.assertEqual(pre[0].appartenance.utilisateur, compte)
        self.assertEqual(pre[0].type, AffectationClasse.CONTRIBUTEUR)

    def test_fonction_caduque_ou_future_ne_donne_pas_acces(self):
        for cause in ("terminee", "expiree", "future", "suspendue"):
            with self.subTest(cause=cause):
                invitation, jeton, pre = self.inviter_avec_fonction(adresse=f"{cause}@example.test")
                ancien_mail = self.message(invitation).body
                if cause == "terminee":
                    pre[0].etat = AffectationClasse.TERMINEE
                elif cause == "suspendue":
                    pre[0].etat = AffectationClasse.SUSPENDUE
                elif cause == "expiree":
                    pre[0].date_debut = timezone.localdate() - timedelta(days=2)
                    pre[0].date_fin = timezone.localdate() - timedelta(days=1)
                else:
                    pre[0].date_debut = timezone.localdate() + timedelta(days=1)
                pre[0].save()
                compte = get_user_model().objects.create_user(cause, email=invitation.email, password=MOT_DE_PASSE)
                reponse = self.client.post(reverse("accepter_invitation", args=[invitation.selecteur, jeton]),
                    {"nom_utilisateur": compte.username, "mot_de_passe": MOT_DE_PASSE})
                if cause in {"expiree", "future"}:
                    self.assertContains(reponse, "pas encore accessible ou plus active")
                else:
                    self.assertNotContains(reponse, "Fonctions conservées")
                self.assertNotContains(reponse, "accessible maintenant")
                self.assertFalse(autorise(compte, ACCEDER_APPLICATION, ecole=self.ecole))
                self.assertIn("Contributeur", ancien_mail)

    def test_expiration_invitation_sans_promouvoir(self):
        invitation, jeton, pre = self.inviter_avec_fonction()
        invitation.expire_le = timezone.now() - timedelta(seconds=1)
        invitation.save()
        reponse = self.client.get(reverse("accepter_invitation", args=[invitation.selecteur, jeton]))
        self.assertContains(reponse, "n’est plus utilisable")
        pre[0].refresh_from_db()
        self.assertIsNone(pre[0].appartenance_id)

    def test_echec_ne_journalise_jamais_le_texte_de_l_exception(self):
        invitation, jeton, _ = self.inviter_avec_fonction()
        lien = "https://ecole.example.test/invitation/" + jeton
        with patch("suivi.services.equipe.EmailMultiAlternatives.send", side_effect=OSError(lien)), \
                self.assertLogs("suivi.services.equipe", level="WARNING") as logs:
            self.assertFalse(envoyer_email_invitation(utilisateur=self.direction, invitation=invitation, lien=lien))
        self.assertTrue(all(jeton not in ligne for ligne in logs.output))
        evenement = EvenementAudit.objects.get(action="invitation.email_echec")
        self.assertEqual(evenement.nouvelles_valeurs, {"erreur": "OSError"})
        invitation.refresh_from_db()
        self.assertEqual(invitation.etat, Invitation.EN_ATTENTE)
        compte = get_user_model().objects.create_user("invitee", email=ADRESSE)
        accepter_invitation(utilisateur=compte, invitation=invitation, jeton=jeton)

    def test_envoi_non_confirme_est_un_echec(self):
        invitation, _, _ = self.inviter_avec_fonction()
        with patch("suivi.services.equipe.EmailMultiAlternatives.send", return_value=0), \
                self.assertLogs("suivi.services.equipe", level="WARNING"):
            self.assertFalse(envoyer_email_invitation(utilisateur=self.direction, invitation=invitation,
                lien="https://ecole.example.test/invitation/fictive/"))
        self.assertEqual(len(mail.outbox), 0)

    def test_texte_lisible_et_html_echappe(self):
        invitation, _, _ = self.inviter_avec_fonction()
        self.ecole.nom = "École A & B <fictive>"
        message = self.message(invitation)
        self.assertIn("École A & B <fictive>", message.body)
        self.assertIn("École A &amp; B &lt;fictive&gt;", message.alternatives[0].content)

    def test_fonction_deja_terminee_absente_du_mail(self):
        invitation, _, pre = self.inviter_avec_fonction()
        pre[0].etat = AffectationClasse.TERMINEE
        pre[0].save()
        self.assertIn("Aucune fonction", self.message(invitation).body)
