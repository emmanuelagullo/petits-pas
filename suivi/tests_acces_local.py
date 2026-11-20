"""Accès sur l'appareil local : clé de secours, dernier recours, liens.

Données fictives uniquement. Le profil local est déclaré par le lanceur :
ces tests le posent explicitement avec `ACCES_LOCAL_AUTONOME`.
"""
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from comptes import secours_local
from comptes.models import (
    AppartenanceEcole, CleSecoursLocale, RecoursLocalEcole, ResponsabiliteEcole, Utilisateur,
)

from .models import Ecole, EvenementAudit
from .services import acces_local

LOCAL = override_settings(MODE_LOCAL=True, ACCES_LOCAL_AUTONOME=True)


def creer_ecole_locale(*, direction=True, noms=("lea",)):
    ecole = Ecole.objects.create(nom="École des Lilas")
    comptes = []
    for nom in noms:
        compte = Utilisateur.objects.create_user(
            nom, password="ancien-mot-de-passe", first_name=nom.title(), last_name="Test")
        appartenance = AppartenanceEcole.objects.create(utilisateur=compte, ecole=ecole)
        if direction and not comptes:
            ResponsabiliteEcole.objects.create(
                appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION)
        comptes.append(compte)
    return ecole, comptes


class CleDeSecours(TestCase):
    def setUp(self):
        self.ecole, (self.lea,) = creer_ecole_locale()

    def test_seule_l_empreinte_est_conservee(self):
        cle = secours_local.creer_cle(self.lea)
        ligne = CleSecoursLocale.objects.get(utilisateur=self.lea)
        self.assertNotIn(cle.replace("-", ""), ligne.empreinte)
        self.assertEqual(len(ligne.empreinte), 64)

    def test_la_cle_retrouve_son_compte_quelle_que_soit_la_saisie(self):
        cle = secours_local.creer_cle(self.lea)
        saisie = " " + cle.lower().replace("-", " ") + " "
        self.assertEqual(secours_local.compte_par_cle(saisie), self.lea)

    def test_une_cle_fausse_ou_mal_formee_ne_retrouve_personne(self):
        secours_local.creer_cle(self.lea)
        self.assertIsNone(secours_local.compte_par_cle("AAAA-AAAA-AAAA-AAAA"))
        self.assertIsNone(secours_local.compte_par_cle("trop court"))
        self.assertIsNone(secours_local.compte_par_cle(""))

    def test_une_nouvelle_cle_remplace_l_ancienne(self):
        ancienne = secours_local.creer_cle(self.lea)
        nouvelle = secours_local.creer_cle(self.lea)
        self.assertNotEqual(ancienne, nouvelle)
        self.assertIsNone(secours_local.compte_par_cle(ancienne))
        self.assertEqual(secours_local.compte_par_cle(nouvelle), self.lea)
        self.assertEqual(CleSecoursLocale.objects.filter(utilisateur=self.lea).count(), 1)

    def test_un_compte_desactive_n_est_pas_retrouve(self):
        cle = secours_local.creer_cle(self.lea)
        # La continuité de direction interdit de désactiver la seule direction.
        Utilisateur.objects.filter(pk=self.lea.pk).update(is_active=False)
        self.assertIsNone(secours_local.compte_par_cle(cle))

    def test_preuve_de_saisie(self):
        cle = secours_local.creer_cle(self.lea)
        self.assertTrue(secours_local.cle_correspond(self.lea, cle.lower()))
        self.assertFalse(secours_local.cle_correspond(self.lea, "AAAA-AAAA-AAAA-AAAA"))


@LOCAL
class ReinitialisationParCle(TestCase):
    def setUp(self):
        self.ecole, (self.lea,) = creer_ecole_locale()
        self.cle = secours_local.creer_cle(self.lea)

    def test_nouveau_mot_de_passe_et_nouvelle_cle(self):
        suivante = acces_local.reinitialiser_par_cle(self.lea, "pomme-lac-vent-jaune")
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password("pomme-lac-vent-jaune"))
        self.assertNotEqual(suivante, self.cle)
        self.assertIsNone(secours_local.compte_par_cle(self.cle))
        self.assertEqual(secours_local.compte_par_cle(suivante), self.lea)

    def test_un_mot_de_passe_refuse_ne_change_rien(self):
        with self.assertRaises(ValidationError):
            acces_local.reinitialiser_par_cle(self.lea, "court")
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password("ancien-mot-de-passe"))
        self.assertEqual(secours_local.compte_par_cle(self.cle), self.lea)

    def test_les_sessions_ouvertes_sont_fermees(self):
        self.client.force_login(self.lea)
        self.assertIn("_auth_user_id", self.client.session)
        acces_local.reinitialiser_par_cle(self.lea, "pomme-lac-vent-jaune")
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_trace_au_journal_de_l_ecole_sans_secret(self):
        acces_local.reinitialiser_par_cle(self.lea, "pomme-lac-vent-jaune")
        evenement = EvenementAudit.objects.get(ecole=self.ecole, action="mot_de_passe_reinitialise")
        self.assertEqual(evenement.nouvelles_valeurs["moyen"], "cle_de_secours")
        self.assertNotIn("pomme", str(evenement.nouvelles_valeurs))
        self.assertNotIn(self.cle.replace("-", ""), str(evenement.nouvelles_valeurs))

    @override_settings(ACCES_LOCAL_AUTONOME=False)
    def test_hors_profil_local_rien_ne_s_ouvre(self):
        with self.assertRaises(PermissionDenied):
            acces_local.reinitialiser_par_cle(self.lea, "pomme-lac-vent-jaune")
        with self.assertRaises(PermissionDenied):
            acces_local.generer_cle(self.lea)


@LOCAL
class DernierRecours(TestCase):
    def setUp(self):
        self.ecole, (self.lea, self.paul) = creer_ecole_locale(noms=("lea", "paul"))

    def test_sans_ligne_le_dernier_recours_n_est_pas_autorise(self):
        self.assertFalse(acces_local.dernier_recours_autorise(self.ecole))
        with self.assertRaises(PermissionDenied):
            acces_local.reinitialiser_dernier_recours(self.lea, "pomme-lac-vent-jaune", self.ecole)

    def test_autorise_il_change_le_mot_de_passe_sans_autre_preuve(self):
        acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=True)
        acces_local.reinitialiser_dernier_recours(self.lea, "pomme-lac-vent-jaune", self.ecole)
        self.lea.refresh_from_db()
        self.assertTrue(self.lea.check_password("pomme-lac-vent-jaune"))
        evenement = EvenementAudit.objects.get(action="mot_de_passe_reinitialise")
        self.assertEqual(evenement.nouvelles_valeurs["moyen"], "dernier_recours")

    def test_seule_la_direction_change_le_choix(self):
        with self.assertRaises(PermissionDenied):
            acces_local.definir_dernier_recours(acteur=self.paul, ecole=self.ecole, autorise_recours=True)
        self.assertFalse(RecoursLocalEcole.objects.exists())

    def test_le_changement_de_choix_est_journalise_une_fois(self):
        for valeur in (True, True, False):
            acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=valeur)
        self.assertEqual(EvenementAudit.objects.filter(action="dernier_recours_local").count(), 2)

    def test_un_compte_etranger_a_l_ecole_est_refuse(self):
        acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=True)
        etranger = Utilisateur.objects.create_user("zoe", password="ancien-mot-de-passe")
        with self.assertRaises(PermissionDenied):
            acces_local.reinitialiser_dernier_recours(etranger, "pomme-lac-vent-jaune", self.ecole)

    @override_settings(ACCES_LOCAL_AUTONOME=False)
    def test_une_seule_cle_ne_suffit_pas(self):
        """MODE_LOCAL seul, sans déclaration du lanceur : jamais de dernier recours."""
        RecoursLocalEcole.objects.create(ecole=self.ecole, dernier_recours=True)
        self.assertFalse(acces_local.dernier_recours_autorise(self.ecole))
        with self.assertRaises(PermissionDenied):
            acces_local.reinitialiser_dernier_recours(self.lea, "pomme-lac-vent-jaune", self.ecole)

    @override_settings(MODE_LOCAL=False, ACCES_LOCAL_AUTONOME=False)
    def test_les_reglages_exigent_les_deux_cles(self):
        from django.conf import settings
        self.assertFalse(settings.ACCES_LOCAL_AUTONOME)


@LOCAL
class LienDeReinitialisation(TestCase):
    def setUp(self):
        self.ecole, (self.lea, self.paul) = creer_ecole_locale(noms=("lea", "paul"))

    def test_la_direction_obtient_un_lien_utilisable(self):
        requete = self.client.get("/").wsgi_request
        lien = acces_local.lien_reinitialisation(
            acteur=self.lea, cible=self.paul, ecole=self.ecole, requete=requete)
        page = self.client.get(lien, follow=True)
        self.assertContains(page, "Choisir un nouveau mot de passe")
        self.assertTrue(EvenementAudit.objects.filter(action="lien_reinitialisation_emis").exists())

    def test_ni_soi_meme_ni_sans_etre_direction(self):
        requete = self.client.get("/").wsgi_request
        with self.assertRaises(ValidationError):
            acces_local.lien_reinitialisation(
                acteur=self.lea, cible=self.lea, ecole=self.ecole, requete=requete)
        with self.assertRaises(ValidationError):
            acces_local.lien_reinitialisation(
                acteur=self.paul, cible=self.lea, ecole=self.ecole, requete=requete)


@LOCAL
class SignalementALaConnexion(TestCase):
    def setUp(self):
        self.ecole, (self.lea, self.paul) = creer_ecole_locale(noms=("lea", "paul"))
        self.hier = timezone.now() - timedelta(days=1)

    def test_le_dernier_recours_est_signale_a_la_direction_et_a_la_personne(self):
        acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=True)
        acces_local.reinitialiser_dernier_recours(self.paul, "pomme-lac-vent-jaune", self.ecole)
        pour_lea = acces_local.reinitialisations_a_signaler(self.lea, self.hier)
        pour_paul = acces_local.reinitialisations_a_signaler(self.paul, self.hier)
        self.assertEqual([e["nom"] for e in pour_lea], ["Paul Test"])
        self.assertTrue(pour_paul[0]["moi"])

    def test_la_reinitialisation_par_cle_n_est_signalee_qu_aux_autres_directions(self):
        secours_local.creer_cle(self.lea)
        acces_local.reinitialiser_par_cle(self.lea, "pomme-lac-vent-jaune")
        self.assertEqual(acces_local.reinitialisations_a_signaler(self.lea, self.hier), [])
        self.assertEqual(acces_local.reinitialisations_a_signaler(self.paul, self.hier), [])

    def test_rien_avant_la_premiere_connexion_ni_apres_la_derniere(self):
        acces_local.definir_dernier_recours(acteur=self.lea, ecole=self.ecole, autorise_recours=True)
        acces_local.reinitialiser_dernier_recours(self.paul, "pomme-lac-vent-jaune", self.ecole)
        self.assertEqual(acces_local.reinitialisations_a_signaler(self.lea, None), [])
        demain = timezone.now() + timedelta(days=1)
        self.assertEqual(acces_local.reinitialisations_a_signaler(self.lea, demain), [])


class LongueurMinimale(TestCase):
    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
         "OPTIONS": {"min_length": 8}}])
    def test_huit_caracteres_passent_quand_le_seuil_est_huit(self):
        validate_password("abcdefgh")
        with self.assertRaises(ValidationError):
            validate_password("abcdefg")

    def test_le_seuil_suit_le_mode(self):
        import importlib, os
        from unittest import mock
        import carnet.settings as reglages
        for local, attendu in (("oui", 8), ("", 12)):
            with mock.patch.dict(os.environ, {"CARNET_MODE_LOCAL": local}):
                recharge = importlib.reload(reglages)
                self.assertEqual(recharge.LONGUEUR_MIN_MOT_DE_PASSE, attendu)
        importlib.reload(reglages)
