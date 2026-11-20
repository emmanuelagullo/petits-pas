"""Écrans de récupération d'accès sur l'appareil local : parcours complets.

Données fictives uniquement ; le profil local est posé par `LOCAL`.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes import secours_local
from comptes.models import AppartenanceEcole, RecoursLocalEcole, Utilisateur

from .models import EvenementAudit
from .services import acces_local
from .tests_acces_local import LOCAL, creer_ecole_locale

NOUVEAU = "pomme-lac-vent-jaune"


@LOCAL
class MotDePasseOublieAvecCle(TestCase):
    def setUp(self):
        self.ecole, (self.lea,) = creer_ecole_locale()
        self.cle = secours_local.creer_cle(self.lea)

    def envoyer(self, **donnees):
        base = {"cle": self.cle, "new_password1": NOUVEAU, "new_password2": NOUVEAU}
        base.update(donnees)
        return self.client.post(reverse("mot_de_passe_oublie"), base)

    def test_la_connexion_propose_le_lien(self):
        page = self.client.get(reverse("connexion"))
        self.assertContains(page, reverse("mot_de_passe_oublie"))
        self.assertNotContains(page, "Contactez la direction de l’école")

    def test_la_page_demande_la_cle_et_un_nouveau_mot_de_passe(self):
        page = self.client.get(reverse("mot_de_passe_oublie"))
        for attendu in ("Clé de secours", "Nouveau mot de passe",
                        f"Au moins {settings.LONGUEUR_MIN_MOT_DE_PASSE} caractères",
                        "Je n’ai plus ma clé de secours"):
            self.assertContains(page, attendu)

    def test_parcours_complet_connexion_et_nouvelle_cle(self):
        reponse = self.envoyer()
        self.assertRedirects(reponse, reverse("cle_secours"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.lea.pk))
        page = self.client.get(reverse("cle_secours"))
        nouvelle = page.context["cle"]
        self.assertNotEqual(nouvelle, self.cle)
        self.assertIsNone(secours_local.compte_par_cle(self.cle))
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password(NOUVEAU))
        suite = self.client.post(reverse("cle_secours"))
        self.assertRedirects(suite, reverse("accueil"), fetch_redirect_response=False)

    def test_une_cle_inconnue_est_signalee_sur_son_champ(self):
        page = self.envoyer(cle="AAAA-AAAA-AAAA-AAAA")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="erreur-cle"')
        self.assertContains(page, 'aria-invalid="true"')
        self.assertContains(page, 'href="#id_cle"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deux_mots_de_passe_differents_ne_changent_rien(self):
        page = self.envoyer(new_password2="autre-chose-encore")
        self.assertContains(page, "pas identiques")
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password("ancien-mot-de-passe"))
        self.assertEqual(secours_local.compte_par_cle(self.cle), self.lea)

    def test_un_mot_de_passe_trop_court_est_refuse_pour_le_compte(self):
        page = self.envoyer(new_password1="court", new_password2="court")
        self.assertContains(page, 'id="erreur-new_password1"')

    def test_sans_dernier_recours_la_page_dit_qu_il_n_y_a_pas_d_autre_issue(self):
        page = self.client.get(reverse("mot_de_passe_oublie"))
        self.assertContains(page, "n’est pas autorisé sur cet appareil")
        self.assertNotContains(page, reverse("dernier_recours"))

    @override_settings(ACCES_LOCAL_AUTONOME=False, EMAIL_DISPONIBLE=False)
    def test_sans_profil_declare_la_page_reste_celle_d_avant(self):
        page = self.client.get(reverse("mot_de_passe_oublie"))
        self.assertContains(page, "Contactez la direction de l’école")
        self.assertNotContains(page, "Clé de secours")
        self.assertEqual(self.client.get(reverse("dernier_recours")).status_code, 404)

    def test_une_idee_de_phrase_est_proposee(self):
        page = self.client.get(reverse("mot_de_passe_oublie"))
        self.assertTrue(re.search(r'id="phrase-proposee">[a-z]+(-[a-z]+){3}<', page.content.decode()))


@LOCAL
class DernierRecoursEcran(TestCase):
    def setUp(self):
        self.ecole, (self.lea,) = creer_ecole_locale()

    def autoriser(self):
        acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=True)

    def test_non_autorise_renvoie_vers_la_page_d_oubli(self):
        reponse = self.client.get(reverse("dernier_recours"))
        self.assertRedirects(reponse, reverse("mot_de_passe_oublie"))
        self.assertEqual(self.client.post(reverse("dernier_recours"), {
            "compte": self.lea.pk, "new_password1": NOUVEAU, "new_password2": NOUVEAU,
        }).status_code, 302)
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password("ancien-mot-de-passe"))

    def test_un_seul_compte_est_nomme_sans_liste(self):
        self.autoriser()
        page = self.client.get(reverse("dernier_recours"))
        self.assertContains(page, "Lea Test")
        self.assertNotContains(page, "<select")

    def test_parcours_complet(self):
        self.autoriser()
        reponse = self.client.post(reverse("dernier_recours"), {
            "compte": self.lea.pk, "new_password1": NOUVEAU, "new_password2": NOUVEAU})
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.lea.pk))
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password(NOUVEAU))
        self.assertTrue(EvenementAudit.objects.filter(
            action="mot_de_passe_reinitialise", nouvelles_valeurs__moyen="dernier_recours").exists())

    def test_plusieurs_comptes_une_liste_et_pas_d_etranger(self):
        paul = Utilisateur.objects.create_user(
            "paul", password="ancien-mot-de-passe", first_name="Paul", last_name="Test")
        AppartenanceEcole.objects.create(utilisateur=paul, ecole=self.ecole)
        self.autoriser()
        page = self.client.get(reverse("dernier_recours"))
        self.assertContains(page, "<select")
        etranger = Utilisateur.objects.create_user("zoe", password="ancien-mot-de-passe")
        refus = self.client.post(reverse("dernier_recours"), {
            "compte": etranger.pk, "new_password1": NOUVEAU, "new_password2": NOUVEAU})
        self.assertContains(refus, "pas proposé sur cet appareil")
        etranger.refresh_from_db()
        self.assertTrue(etranger.check_password("ancien-mot-de-passe"))

    def test_la_page_d_oubli_propose_le_dernier_recours_quand_il_est_autorise(self):
        self.autoriser()
        self.assertContains(self.client.get(reverse("mot_de_passe_oublie")), reverse("dernier_recours"))


@LOCAL
class MonCompteEtReglageDeLEcole(TestCase):
    def setUp(self):
        self.ecole, (self.lea, self.paul) = creer_ecole_locale(noms=("lea", "paul"))

    def test_nouvelle_cle_depuis_mon_compte(self):
        ancienne = secours_local.creer_cle(self.lea)
        self.client.force_login(self.lea)
        self.assertContains(self.client.get(reverse("mon_compte")), "Obtenir une nouvelle clé de secours")
        reponse = self.client.post(reverse("mon_compte"), {"action": "nouvelle_cle_secours"})
        self.assertRedirects(reponse, reverse("cle_secours"))
        nouvelle = self.client.get(reverse("cle_secours")).context["cle"]
        self.assertIsNone(secours_local.compte_par_cle(ancienne))
        self.assertEqual(secours_local.compte_par_cle(nouvelle), self.lea)
        retour = self.client.post(reverse("cle_secours"))
        self.assertRedirects(retour, reverse("mon_compte"), fetch_redirect_response=False)

    def test_sans_cle_la_page_le_dit(self):
        self.client.force_login(self.lea)
        page = self.client.get(reverse("mon_compte"))
        self.assertContains(page, "Obtenir une clé de secours")
        self.assertContains(page, "Vous n’avez pas de clé de secours")

    @override_settings(ACCES_LOCAL_AUTONOME=False)
    def test_hors_profil_local_mon_compte_ne_propose_rien(self):
        self.client.force_login(self.lea)
        self.assertNotContains(self.client.get(reverse("mon_compte")), "clé de secours")
        self.assertEqual(
            self.client.post(reverse("mon_compte"), {"action": "nouvelle_cle_secours"}).status_code, 404)

    def test_la_direction_autorise_sans_cle_mais_n_interdit_qu_avec_sa_cle(self):
        cle = secours_local.creer_cle(self.lea)
        self.client.force_login(self.lea)
        self.assertContains(self.client.get(reverse("gestion")), reverse("acces_local_ecole"))
        self.client.post(reverse("acces_local_ecole"), {"dernier_recours": "on"})
        self.assertTrue(acces_local.dernier_recours_autorise(self.ecole))
        sans = self.client.post(reverse("acces_local_ecole"), {})
        self.assertContains(sans, "recopiez votre clé de secours")
        self.assertTrue(acces_local.dernier_recours_autorise(self.ecole))
        fausse = self.client.post(reverse("acces_local_ecole"), {"cle": "AAAA-AAAA-AAAA-AAAA"})
        self.assertContains(fausse, 'aria-invalid="true"')
        bonne = self.client.post(reverse("acces_local_ecole"), {"cle": cle.lower()})
        self.assertRedirects(bonne, reverse("gestion"), fetch_redirect_response=False)
        self.assertFalse(acces_local.dernier_recours_autorise(self.ecole))

    def test_seule_la_direction_voit_le_reglage(self):
        self.client.force_login(self.paul)
        self.assertEqual(self.client.get(reverse("acces_local_ecole")).status_code, 403)
        self.assertFalse(RecoursLocalEcole.objects.exists())

    @override_settings(ACCES_LOCAL_AUTONOME=False)
    def test_le_reglage_n_existe_pas_hors_profil_local(self):
        self.client.force_login(self.lea)
        self.assertEqual(self.client.get(reverse("acces_local_ecole")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("gestion")), "Accès sur cet appareil")


@LOCAL
class LienDepuisLEquipe(TestCase):
    def setUp(self):
        self.ecole, (self.lea, self.paul) = creer_ecole_locale(noms=("lea", "paul"))

    def test_la_direction_obtient_un_lien_une_seule_fois(self):
        self.client.force_login(self.lea)
        appartenance = self.paul.appartenances_ecoles.get()
        reponse = self.client.post(reverse("equipe_ecole"), {
            "action": "lien_reinitialisation", "appartenance": appartenance.pk, "vue": "personnes"},
            follow=True)
        self.assertContains(reponse, "Lien pour Paul Test")
        lien = re.search(r'id="lien-reinitialisation" value="([^"]+)"', reponse.content.decode()).group(1)
        self.assertContains(self.client.get(reverse("equipe_ecole") + "?vue=personnes"), "Obtenir un lien")
        self.assertNotContains(self.client.get(reverse("equipe_ecole") + "?vue=personnes"),
                               "Lien pour Paul Test")
        self.client.logout()
        page = self.client.get(lien, follow=True)
        self.assertContains(page, "Choisir un nouveau mot de passe")
        self.assertContains(page, "Minimum 12 caractères" if not self.settings_local() else "Minimum 8")

    def settings_local(self):
        from django.conf import settings
        return settings.LONGUEUR_MIN_MOT_DE_PASSE == 8

    def test_pas_de_bouton_pour_soi_meme(self):
        self.client.force_login(self.lea)
        page = self.client.get(reverse("equipe_ecole") + "?vue=personnes")
        self.assertEqual(page.content.decode().count('value="lien_reinitialisation"'), 1)

    @override_settings(ACCES_LOCAL_AUTONOME=False)
    def test_hors_profil_local_pas_de_bouton(self):
        self.client.force_login(self.lea)
        self.assertNotContains(self.client.get(reverse("equipe_ecole") + "?vue=personnes"),
                               "lien_reinitialisation")


@LOCAL
class SignalementALaConnexionEcran(TestCase):
    def test_la_direction_voit_le_dernier_recours_d_un_collegue(self):
        ecole, (lea, paul) = creer_ecole_locale(noms=("lea", "paul"))
        acces_local.definir_dernier_recours(acteur=lea, ecole=ecole, autorise_recours=True)
        Utilisateur.objects.filter(pk=lea.pk).update(last_login=timezone.now() - timedelta(days=1))
        acces_local.reinitialiser_dernier_recours(paul, NOUVEAU, ecole)
        reponse = self.client.post(reverse("connexion"), {
            "nom_utilisateur": "lea", "mot_de_passe": "ancien-mot-de-passe"}, follow=True)
        textes = [str(m) for m in get_messages(reponse.wsgi_request)]
        self.assertTrue(any("Le mot de passe de Paul Test a été réinitialisé" in t for t in textes), textes)
