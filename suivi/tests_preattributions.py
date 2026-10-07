"""Pré-attributions de fonction à une invitation : fin à la révocation ou à
l'expiration, affichage, et adresse de la personne invitée (réservée à la
direction)."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comptes.models import AffectationClasse, AppartenanceEcole, Invitation, ResponsabiliteEcole

from .models import Classe, Ecole, EvenementAudit
from .services.equipe import inviter, revoquer_invitation, attribuer_affectation, terminer_affectation

MOT_DE_PASSE = "École ! Rivière 2026 solide"
ADRESSE = "invitee@example.test"


class BasePreattributions(TestCase):
    def setUp(self):
        self.ecole = Ecole.objects.create(nom="École A")
        self.classe = Classe.objects.create(ecole=self.ecole, nom="A1")
        self.autre_classe = Classe.objects.create(ecole=self.ecole, nom="A2")
        self.direction = self._membre("direction")
        ResponsabiliteEcole.objects.create(appartenance=self.direction_a)
        self.responsable = self._membre("responsable", AffectationClasse.RESPONSABLE)
        self.associe = self._membre("associe", AffectationClasse.ENSEIGNANT_ASSOCIE)
        self.contributeur = self._membre("contributeur", AffectationClasse.CONTRIBUTEUR)
        AffectationClasse.objects.create(
            appartenance=self.responsable_a, classe=self.autre_classe,
            type=AffectationClasse.RESPONSABLE)
        self.classe.activer()
        self.autre_classe.activer()
        self.url_collaborateurs = reverse("collaborateurs_classe", args=[self.classe.pk])

    def _membre(self, nom, fonction=None):
        utilisateur = get_user_model().objects.create_user(
            nom, email=f"{nom}@example.test", password=MOT_DE_PASSE)
        appartenance = AppartenanceEcole.objects.create(utilisateur=utilisateur, ecole=self.ecole)
        setattr(self, f"{nom}_a", appartenance)
        if fonction:
            AffectationClasse.objects.create(
                appartenance=appartenance, classe=self.classe, type=fonction)
        return utilisateur

    def inviter_avec_fonction(self, adresse=ADRESSE, classes=None, type=AffectationClasse.CONTRIBUTEUR):
        invitation, jeton = inviter(utilisateur=self.direction, ecole=self.ecole, email=adresse)
        preattributions = [
            attribuer_affectation(utilisateur=self.direction, classe=classe, type=type, invitation=invitation)
            for classe in (classes or [self.classe])
        ]
        return invitation, jeton, preattributions

    def entrer(self, utilisateur):
        client = self.client
        client.get(reverse("deconnexion"))
        client.post(reverse("connexion"), {
            "nom_utilisateur": utilisateur.username, "mot_de_passe": MOT_DE_PASSE})
        return client

    def equipe(self, historique=False):
        return self.client.get(
            reverse("equipe_ecole") + "?vue=classes" + ("&historique=1" if historique else "")
        ).content.decode()


class FinALaRevocation(BasePreattributions):
    def test_la_revocation_termine_les_preattributions(self):
        invitation, _, pre = self.inviter_avec_fonction(classes=[self.classe, self.autre_classe])
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        for affectation in pre:
            affectation.refresh_from_db()
            self.assertEqual(affectation.etat, AffectationClasse.TERMINEE)
            self.assertEqual(affectation.termine_par, self.direction)
            self.assertIsNotNone(affectation.termine_le)
            self.assertEqual(affectation.date_fin, timezone.localdate())
            self.assertIn("Invitation révoquée", affectation.motif)
            self.assertFalse(affectation.preattribution_en_cours)
            self.assertIsNone(affectation.appartenance_id)

    def test_la_revocation_est_journalisee_pour_chaque_pre_attribution(self):
        invitation, _, pre = self.inviter_avec_fonction(classes=[self.classe, self.autre_classe])
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        evenements = EvenementAudit.objects.filter(action="affectation.terminee")
        self.assertEqual(evenements.count(), 2)
        for evenement in evenements:
            self.assertEqual(evenement.acteur, self.direction)
            self.assertEqual(evenement.ecole, self.ecole)
            self.assertEqual(evenement.anciennes_valeurs["etat"], "active")
            self.assertEqual(evenement.nouvelles_valeurs["cause"], "invitation_revoquee")

    def test_le_motif_d_origine_est_conserve(self):
        invitation, _ = inviter(utilisateur=self.direction, ecole=self.ecole, email=ADRESSE)
        pre = attribuer_affectation(
            utilisateur=self.direction, classe=self.classe, type=AffectationClasse.CONTRIBUTEUR,
            invitation=invitation, motif="Remplacement de congé")
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        pre.refresh_from_db()
        self.assertEqual(pre.motif, "Remplacement de congé | Invitation révoquée")

    def test_une_invitation_sans_fonction_se_revoque_toujours(self):
        invitation, _ = inviter(utilisateur=self.direction, ecole=self.ecole, email=ADRESSE)
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        invitation.refresh_from_db()
        self.assertEqual(invitation.etat, Invitation.REVOQUEE)

    def test_les_pre_attributions_des_autres_invitations_ne_sont_pas_touchees(self):
        invitation, _, _ = self.inviter_avec_fonction()
        _, _, autres = self.inviter_avec_fonction(adresse="autre@example.test")
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        autres[0].refresh_from_db()
        self.assertEqual(autres[0].etat, AffectationClasse.ACTIVE)
        self.assertTrue(autres[0].preattribution_en_cours)

    def test_une_affectation_reelle_n_est_jamais_touchee(self):
        invitation, _, _ = self.inviter_avec_fonction()
        reelle = AffectationClasse.objects.get(appartenance=self.contributeur_a)
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        reelle.refresh_from_db()
        self.assertEqual(reelle.etat, AffectationClasse.ACTIVE)

    def test_une_pre_attribution_deja_annulee_n_est_pas_terminee_deux_fois(self):
        invitation, _, pre = self.inviter_avec_fonction()
        terminer_affectation(utilisateur=self.direction, affectation=pre[0])
        avant = EvenementAudit.objects.filter(action="affectation.terminee").count()
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        self.assertEqual(EvenementAudit.objects.filter(action="affectation.terminee").count(), avant)

    def test_seule_la_direction_revoque(self):
        invitation, _, pre = self.inviter_avec_fonction()
        with self.assertRaises(Exception):
            revoquer_invitation(utilisateur=self.contributeur, invitation=invitation)
        pre[0].refresh_from_db()
        self.assertEqual(pre[0].etat, AffectationClasse.ACTIVE)


class FinALExpiration(BasePreattributions):
    def expirer(self, invitation):
        Invitation.objects.filter(pk=invitation.pk).update(expire_le=timezone.now() - timedelta(days=1))
        sortie = StringIO()
        call_command("marquer_invitations_expirees", stdout=sortie)
        return sortie.getvalue()

    def test_l_expiration_termine_les_pre_attributions(self):
        invitation, _, pre = self.inviter_avec_fonction(classes=[self.classe, self.autre_classe])
        self.assertIn("1 invitation(s) marquée(s) expirée(s)", self.expirer(invitation))
        invitation.refresh_from_db()
        self.assertEqual(invitation.etat, Invitation.EXPIREE)
        for affectation in pre:
            affectation.refresh_from_db()
            self.assertEqual(affectation.etat, AffectationClasse.TERMINEE)
            self.assertIsNone(affectation.termine_par)
            self.assertIn("Invitation expirée", affectation.motif)

    def test_l_expiration_automatique_n_ecrit_rien_au_journal(self):
        invitation, _, _ = self.inviter_avec_fonction()
        self.expirer(invitation)
        self.assertFalse(EvenementAudit.objects.filter(action="affectation.terminee").exists())

    def test_les_invitations_valables_ne_sont_pas_touchees(self):
        valable, _, pre_valable = self.inviter_avec_fonction(adresse="valable@example.test")
        expiree, _, pre_expiree = self.inviter_avec_fonction()
        self.expirer(expiree)
        valable.refresh_from_db(); pre_valable[0].refresh_from_db()
        self.assertEqual(valable.etat, Invitation.EN_ATTENTE)
        self.assertEqual(pre_valable[0].etat, AffectationClasse.ACTIVE)

    def test_relancer_la_commande_ne_change_plus_rien(self):
        invitation, _, _ = self.inviter_avec_fonction()
        self.expirer(invitation)
        self.assertIn("0 invitation(s)", self.expirer(invitation))

    def test_une_invitation_acceptee_n_est_pas_expiree(self):
        invitation, _, pre = self.inviter_avec_fonction()
        Invitation.objects.filter(pk=invitation.pk).update(etat=Invitation.ACCEPTEE)
        Invitation.objects.filter(pk=invitation.pk).update(expire_le=timezone.now() - timedelta(days=1))
        call_command("marquer_invitations_expirees", stdout=StringIO())
        pre[0].refresh_from_db()
        self.assertEqual(pre[0].etat, AffectationClasse.ACTIVE)


class PreattributionEnCours(BasePreattributions):
    def test_en_cours_tant_que_l_invitation_est_valable(self):
        _, _, pre = self.inviter_avec_fonction()
        self.assertTrue(pre[0].preattribution_en_cours)

    def test_plus_en_cours_des_que_l_invitation_ne_l_est_plus(self):
        for etat in (Invitation.REVOQUEE, Invitation.EXPIREE, Invitation.ACCEPTEE):
            with self.subTest(etat):
                invitation, _, pre = self.inviter_avec_fonction(adresse=f"{etat}@example.test")
                Invitation.objects.filter(pk=invitation.pk).update(etat=etat)
                pre[0].refresh_from_db()
                self.assertFalse(pre[0].preattribution_en_cours)

    def test_plus_en_cours_si_la_date_limite_est_passee_meme_sans_la_commande(self):
        invitation, _, pre = self.inviter_avec_fonction()
        Invitation.objects.filter(pk=invitation.pk).update(expire_le=timezone.now() - timedelta(minutes=1))
        pre[0].refresh_from_db()
        self.assertEqual(Invitation.objects.get(pk=invitation.pk).etat, Invitation.EN_ATTENTE)
        self.assertFalse(pre[0].preattribution_en_cours)

    def test_plus_en_cours_apres_annulation_par_la_direction(self):
        _, _, pre = self.inviter_avec_fonction()
        terminer_affectation(utilisateur=self.direction, affectation=pre[0])
        pre[0].refresh_from_db()
        self.assertFalse(pre[0].preattribution_en_cours)

    def test_une_affectation_reelle_n_est_pas_une_pre_attribution(self):
        reelle = AffectationClasse.objects.get(appartenance=self.contributeur_a)
        self.assertFalse(reelle.preattribution_en_cours)


class PageCollaborateurs(BasePreattributions):
    def test_une_pre_attribution_en_cours_est_listee(self):
        self.inviter_avec_fonction()
        self.entrer(self.contributeur)
        page = self.client.get(self.url_collaborateurs).content.decode()
        self.assertIn("Invitation en cours", page)

    def test_l_adresse_n_est_visible_que_de_la_direction(self):
        self.inviter_avec_fonction()
        self.entrer(self.direction)
        direction = self.client.get(self.url_collaborateurs).content.decode()
        self.assertIn(ADRESSE, direction)
        for nom in ("contributeur", "associe", "responsable"):
            with self.subTest(nom):
                self.entrer(getattr(self, nom))
                reponse = self.client.get(self.url_collaborateurs)
                self.assertEqual(reponse.status_code, 200)
                page = reponse.content.decode()
                self.assertNotIn(ADRESSE, page)
                self.assertNotIn("invitee", page)
                self.assertIn("Invitation en cours", page)
                self.assertIn("personne invitée", page)

    def test_les_collaborateurs_nommes_restent_affiches_pour_tous(self):
        self.entrer(self.contributeur)
        page = self.client.get(self.url_collaborateurs).content.decode()
        for nom in ("direction", "responsable", "associe", "contributeur"):
            if nom != "direction":
                self.assertIn(nom, page)

    def test_aucune_pre_attribution_revoquee_expiree_ou_annulee_n_apparait(self):
        revoquee, _, _ = self.inviter_avec_fonction(adresse="revoquee@example.test")
        expiree, _, _ = self.inviter_avec_fonction(adresse="expiree@example.test")
        annulee, _, pre_annulee = self.inviter_avec_fonction(adresse="annulee@example.test")
        revoquer_invitation(utilisateur=self.direction, invitation=revoquee)
        Invitation.objects.filter(pk=expiree.pk).update(expire_le=timezone.now() - timedelta(days=1))
        call_command("marquer_invitations_expirees", stdout=StringIO())
        terminer_affectation(utilisateur=self.direction, affectation=pre_annulee[0])
        for utilisateur in (self.direction, self.contributeur):
            self.entrer(utilisateur)
            page = self.client.get(self.url_collaborateurs).content.decode()
            for adresse in ("revoquee", "expiree", "annulee"):
                self.assertNotIn(adresse, page)
            self.assertNotIn("Invitation en cours", page)

    def test_donnees_anciennes_une_ligne_restee_active_apres_revocation_n_apparait_pas(self):
        invitation, _, pre = self.inviter_avec_fonction(adresse="ancienne@example.test")
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        # Etat d'avant la correction : la pré-attribution était restée active.
        AffectationClasse.objects.filter(pk=pre[0].pk).update(etat=AffectationClasse.ACTIVE, date_fin=None)
        self.entrer(self.direction)
        page = self.client.get(self.url_collaborateurs).content.decode()
        self.assertNotIn("ancienne", page)
        self.assertNotIn("Invitation en cours", page)

    def test_l_acces_reste_reserve_aux_personnes_de_la_classe(self):
        self.inviter_avec_fonction()
        etranger = get_user_model().objects.create_user("etranger", password=MOT_DE_PASSE)
        AppartenanceEcole.objects.create(utilisateur=etranger, ecole=self.ecole)
        self.entrer(etranger)
        self.assertNotEqual(self.client.get(self.url_collaborateurs).status_code, 200)


class PageEquipe(BasePreattributions):
    def test_en_cours_gerable_avec_l_adresse(self):
        self.inviter_avec_fonction()
        self.entrer(self.direction)
        page = self.equipe()
        self.assertIn("Invitation en cours", page)
        self.assertIn(ADRESSE, page)
        self.assertIn("Annuler la pré-attribution", page)

    def test_apres_revocation_plus_d_invitation_en_cours_ni_de_bouton(self):
        invitation, _, _ = self.inviter_avec_fonction()
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        self.entrer(self.direction)
        courante = self.equipe()
        self.assertNotIn("Invitation en cours", courante)
        self.assertNotIn("Annuler la pré-attribution", courante)
        historique = self.equipe(historique=True)
        self.assertIn("Pré-attribution annulée", historique)
        self.assertIn("annulée le", historique)
        self.assertNotIn("Invitation en cours", historique)
        self.assertNotIn("Annuler la pré-attribution", historique)

    def test_donnees_anciennes_restees_actives_ne_proposent_plus_d_annuler(self):
        invitation, _, pre = self.inviter_avec_fonction()
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        AffectationClasse.objects.filter(pk=pre[0].pk).update(
            etat=AffectationClasse.ACTIVE, date_fin=None, termine_par=None, termine_le=None)
        self.entrer(self.direction)
        for historique in (False, True):
            page = self.equipe(historique=historique)
            self.assertNotIn("Invitation en cours", page)
            self.assertNotIn("Annuler la pré-attribution", page)
        self.assertIn("Pré-attribution annulée", self.equipe(historique=True))

    def test_l_annulation_par_la_direction_reste_possible(self):
        _, _, pre = self.inviter_avec_fonction()
        self.entrer(self.direction)
        reponse = self.client.post(reverse("equipe_ecole"), {
            "action": "terminer_affectation", "affectation": pre[0].pk, "vue": "classes"})
        self.assertIn(reponse.status_code, (200, 302))
        pre[0].refresh_from_db()
        self.assertEqual(pre[0].etat, AffectationClasse.TERMINEE)


class PageAcceptation(BasePreattributions):
    def test_une_fonction_annulee_n_est_pas_presentee_a_la_personne_invitee(self):
        invitation, jeton, pre = self.inviter_avec_fonction(classes=[self.classe, self.autre_classe])
        terminer_affectation(utilisateur=self.direction, affectation=pre[1])
        lien = reverse("accepter_invitation", args=[invitation.selecteur, jeton])
        reponse = self.client.post(lien, {
            "username": "nouvelle", "first_name": "Nou", "last_name": "Velle",
            "password1": MOT_DE_PASSE, "password2": MOT_DE_PASSE})
        self.assertEqual(reponse.status_code, 200)
        fonctions = reponse.context["fonctions_preattribuees"]
        self.assertEqual([f.classe for f in fonctions], [self.classe])

    def test_une_invitation_revoquee_n_est_plus_acceptable(self):
        invitation, jeton, _ = self.inviter_avec_fonction()
        revoquer_invitation(utilisateur=self.direction, invitation=invitation)
        lien = reverse("accepter_invitation", args=[invitation.selecteur, jeton])
        reponse = self.client.post(lien, {
            "username": "nouvelle", "first_name": "Nou", "last_name": "Velle",
            "password1": MOT_DE_PASSE, "password2": MOT_DE_PASSE})
        self.assertFalse(get_user_model().objects.filter(username="nouvelle").exists())
