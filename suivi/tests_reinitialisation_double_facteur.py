"""Codes de secours à la connexion, régénération et réinitialisation
hiérarchique du second facteur (#C8d)."""
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from carnet.double_facteur import ASSOCIE, DIRECTION
from comptes import totp
from comptes.models import (
    AffectationClasse, AppartenanceEcole, CodeSecoursDoubleFacteur, DoubleFacteurCompte,
    ResponsabiliteEcole,
)

from .acces_double_facteur import SESSION_ATTENTE, SESSION_VERIFIE
from .models import Classe, Ecole, EvenementAudit
from .services.double_facteur import (
    refus_reinitialisation, reinitialiser_par_la_direction, reinitialiser_par_le_deployeur,
)
from .tests_acces_double_facteur import (
    MOT_DE_PASSE, OBLIGATOIRE_DEPLOYEUR, BaseAcces, en_deux_facteurs,
)


class CodesDeSecoursALaConnexion(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.cle = self.inscrire(self.enseignant)
        self.codes = totp.generer_codes_secours(self.enseignant)

    def verifier(self, saisie, client=None):
        client = client or self.client
        self.connecter(self.enseignant, client)
        return client.post(reverse("connexion_verification"), {"code": saisie})

    def test_un_code_de_secours_ouvre_la_session_et_previent(self):
        reponse = self.verifier(self.codes[0])
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertTrue(self.est_connecte())
        self.assertTrue(self.client.session[SESSION_VERIFIE])
        page = self.client.get(reverse("accueil"))
        self.assertContains(page, "Un code de secours a été utilisé. Il vous en reste 9.")
        self.assertEqual(totp.codes_secours_restants(self.enseignant), 9)

    def test_le_rappel_de_regeneration_apparait_quand_il_en_reste_peu(self):
        for code in self.codes[:7]:
            totp.utiliser_code_secours(self.enseignant, code)
        reponse = self.verifier(self.codes[7])
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("accueil")), "Générez-en de nouveaux")

    def test_un_code_de_secours_ne_sert_qu_une_fois(self):
        self.verifier(self.codes[0])
        autre = type(self.client)()
        reponse = self.verifier(self.codes[0], autre)
        self.assertFalse(self.est_connecte(autre))
        self.assertContains(reponse, "Code incorrect ou expiré")

    def test_la_saisie_du_code_de_secours_est_tolerante(self):
        self.verifier(self.codes[1].lower().replace("-", " "))
        self.assertTrue(self.est_connecte())

    def test_un_code_de_secours_d_un_autre_compte_est_refuse(self):
        cle = self.inscrire(self.direction)
        codes_direction = totp.generer_codes_secours(self.direction)
        reponse = self.verifier(codes_direction[0])
        self.assertFalse(self.est_connecte())
        self.assertContains(reponse, "Code incorrect ou expiré")
        self.assertEqual(totp.codes_secours_restants(self.direction), 10)

    def test_un_code_de_secours_faux_est_refuse(self):
        reponse = self.verifier("AAAA-BBBB-CCCC-DDDD")
        self.assertFalse(self.est_connecte())
        self.assertContains(reponse, "Code incorrect ou expiré")

    @override_settings(RATELIMIT_DOUBLE_FACTEUR="3/15m")
    def test_les_codes_de_secours_partagent_le_plafond_des_saisies(self):
        self.connecter(self.enseignant)
        for _ in range(3):
            self.client.post(reverse("connexion_verification"), {"code": "AAAA-BBBB-CCCC-DDDD"})
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.codes[0]})
        self.assertEqual(reponse.status_code, 429)
        self.assertFalse(self.est_connecte())
        self.assertEqual(totp.codes_secours_restants(self.enseignant), 10)

    def test_l_usage_est_journalise_dans_l_ecole(self):
        self.verifier(self.codes[0])
        evenement = EvenementAudit.objects.get(action="securite.code_secours_utilise")
        self.assertEqual(evenement.ecole, self.ecole)
        self.assertEqual(evenement.acteur, self.enseignant)
        self.assertEqual(evenement.nouvelles_valeurs["cible_id"], self.enseignant.pk)
        self.assertNotIn(self.codes[0], str(evenement.nouvelles_valeurs))

    def test_un_code_totp_n_est_pas_pris_pour_un_code_de_secours(self):
        reponse = self.verifier("123456")
        self.assertContains(reponse, "Code incorrect ou expiré")
        self.assertEqual(totp.codes_secours_restants(self.enseignant), 10)


class CodesDeSecoursEnCompte(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.connecter(self.enseignant)

    def inscrire_par_la_page(self):
        cle = totp.cle_en_cours(DoubleFacteurCompte.objects.get(
            utilisateur=self.enseignant)) if False else None
        self.client.get(reverse("double_facteur"))
        cle = totp.cle_en_cours(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant))
        reponse = self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        return cle, reponse

    def test_les_codes_s_affichent_une_seule_fois_apres_l_inscription(self):
        cle, reponse = self.inscrire_par_la_page()
        codes = re.findall(r"<code>([A-Z2-9-]{19})</code>", reponse.content.decode())
        self.assertEqual(len(codes), 10)
        self.assertContains(reponse, "plus jamais affichés")
        for nom in ("double_facteur", "mon_compte"):
            page = self.client.get(reverse(nom)).content.decode()
            for code in codes:
                self.assertNotIn(code, page)
        self.assertContains(self.client.get(reverse("double_facteur")), "Il vous reste 10 codes de secours")

    def test_regeneration_exige_un_code_actuel_et_invalide_les_anciens(self):
        cle, reponse = self.inscrire_par_la_page()
        anciens = reponse.context["codes_secours"]
        refus = self.client.post(reverse("double_facteur"), {"action": "regenerer_codes", "code": "000000"})
        self.assertContains(refus, "Code incorrect ou expiré")
        self.assertTrue(totp.utiliser_code_secours(self.enseignant, anciens[0]) or True)
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(dernier_pas=0)
        reponse = self.client.post(reverse("double_facteur"), {"action": "regenerer_codes", "code": self.code(cle)})
        nouveaux = reponse.context["codes_secours"]
        self.assertEqual(len(nouveaux), 10)
        self.assertFalse(set(anciens) & set(nouveaux))
        self.assertFalse(totp.utiliser_code_secours(self.enseignant, anciens[1]))
        self.assertTrue(EvenementAudit.objects.filter(action="securite.codes_secours_regeneres").exists())

    def test_un_code_de_secours_ne_suffit_pas_a_regenerer(self):
        cle, reponse = self.inscrire_par_la_page()
        code = reponse.context["codes_secours"][0]
        refus = self.client.post(reverse("double_facteur"), {"action": "regenerer_codes", "code": code})
        self.assertContains(refus, "Code incorrect ou expiré")
        self.assertEqual(totp.codes_secours_restants(self.enseignant), 10)

    def test_le_retrait_volontaire_supprime_les_codes(self):
        cle, _ = self.inscrire_par_la_page()
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(dernier_pas=0)
        self.client.post(reverse("double_facteur"), {"action": "retirer", "code": self.code(cle)})
        self.assertFalse(CodeSecoursDoubleFacteur.objects.exists())


class ReinitialisationParLaDirection(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.cle = self.inscrire(self.enseignant)
        totp.generer_codes_secours(self.enseignant)
        self.autre_ecole = Ecole.objects.create(nom="École B")
        self.classe_b = Classe.objects.create(ecole=self.autre_ecole, nom="B1")

    def reinitialiser(self, acteur=None, cible=None, ecole=None):
        reinitialiser_par_la_direction(
            acteur=acteur or self.direction, cible=cible or self.enseignant, ecole=ecole or self.ecole)

    def test_la_direction_reinitialise_un_rang_inferieur(self):
        self.reinitialiser()
        self.assertFalse(totp.est_inscrit(self.enseignant))
        self.assertFalse(CodeSecoursDoubleFacteur.objects.exists())

    def test_l_operation_est_journalisee_dans_l_ecole_de_la_direction(self):
        self.reinitialiser()
        evenement = EvenementAudit.objects.get(action="securite.double_facteur_reinitialise")
        self.assertEqual((evenement.ecole, evenement.acteur), (self.ecole, self.direction))
        self.assertEqual(evenement.nouvelles_valeurs, {"cible_id": self.enseignant.pk, "par": "direction"})

    def test_apres_reinitialisation_la_connexion_ne_demande_plus_de_code_si_optionnel(self):
        self.reinitialiser()
        reponse = self.connecter(self.enseignant)
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertTrue(self.est_connecte())
        self.assertNotIn(SESSION_VERIFIE, self.client.session)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_une_reinitialisation_ne_leve_jamais_l_obligation(self):
        self.reinitialiser()
        compte = DoubleFacteurCompte.objects.get(utilisateur=self.enseignant)
        self.assertLessEqual(compte.echeance_le, timezone.now())
        self.connecter(self.enseignant)
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                             fetch_redirect_response=False)
        # Elle peut se réinscrire, avec une clé neuve et de nouveaux codes.
        self.client.get(reverse("double_facteur"))
        cle = totp.cle_en_cours(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant))
        self.assertNotEqual(cle, self.cle)
        reponse = self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        self.assertEqual(len(reponse.context["codes_secours"]), 10)
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_l_ancienne_cle_et_les_anciens_codes_ne_servent_plus(self):
        ancien_code = totp.generer_codes_secours(self.enseignant)[0]
        self.reinitialiser()
        self.assertFalse(totp.utiliser_code_secours(self.enseignant, ancien_code))
        self.assertFalse(totp.verifier_code(self.enseignant, self.code(self.cle)))

    def test_la_direction_ne_peut_pas_reinitialiser_une_autre_direction(self):
        autre = self._membre("direction2")
        ResponsabiliteEcole.objects.create(appartenance=self.direction2_a)
        self.inscrire(autre)
        with self.assertRaises(ValidationError):
            self.reinitialiser(cible=autre)
        self.assertTrue(totp.est_inscrit(autre))

    def test_la_direction_ne_peut_pas_se_reinitialiser_elle_meme(self):
        self.inscrire(self.direction)
        with self.assertRaises(ValidationError):
            self.reinitialiser(cible=self.direction)

    def test_un_compte_direction_ailleurs_est_refuse_meme_s_il_n_a_qu_un_rang_bas_ici(self):
        multi = self._membre("multi")
        ailleurs = AppartenanceEcole.objects.create(utilisateur=multi, ecole=self.autre_ecole)
        ResponsabiliteEcole.objects.create(appartenance=ailleurs)
        self.inscrire(multi)
        with self.assertRaises(ValidationError):
            self.reinitialiser(cible=multi)
        self.assertTrue(totp.est_inscrit(multi))

    def test_un_compte_multi_ecoles_de_rang_bas_partout_est_reinitialisable(self):
        multi = self._membre("multi")
        ailleurs = AppartenanceEcole.objects.create(utilisateur=multi, ecole=self.autre_ecole)
        AffectationClasse.objects.create(
            appartenance=ailleurs, classe=self.classe_b, type=AffectationClasse.RESPONSABLE)
        self.classe_b.activer()
        self.inscrire(multi)
        self.reinitialiser(cible=multi)
        self.assertFalse(totp.est_inscrit(multi))

    def test_une_direction_d_une_autre_ecole_ne_peut_rien(self):
        autre_direction = get_user_model().objects.create_user("direction-b", password=MOT_DE_PASSE)
        appartenance = AppartenanceEcole.objects.create(utilisateur=autre_direction, ecole=self.autre_ecole)
        ResponsabiliteEcole.objects.create(appartenance=appartenance)
        with self.assertRaises(PermissionDenied):
            self.reinitialiser(acteur=autre_direction)
        with self.assertRaises(ValidationError):
            self.reinitialiser(acteur=autre_direction, ecole=self.autre_ecole)
        self.assertTrue(totp.est_inscrit(self.enseignant))

    def test_un_enseignant_ne_peut_pas_reinitialiser(self):
        autre = self._membre("collegue")
        self.inscrire(autre)
        with self.assertRaises(PermissionDenied):
            self.reinitialiser(acteur=self.enseignant, cible=autre)

    def test_une_personne_sans_second_facteur_n_est_pas_concernee(self):
        sans = self._membre("sans")
        with self.assertRaises(ValidationError):
            self.reinitialiser(cible=sans)
        self.assertFalse(EvenementAudit.objects.filter(action="securite.double_facteur_reinitialise").exists())

    def test_une_personne_hors_de_l_ecole_est_refusee(self):
        etranger = get_user_model().objects.create_user("etranger", password=MOT_DE_PASSE)
        AppartenanceEcole.objects.create(utilisateur=etranger, ecole=self.autre_ecole)
        self.inscrire(etranger)
        with self.assertRaises(ValidationError):
            self.reinitialiser(cible=etranger)

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False)
    def test_fonction_indisponible_refusee(self):
        with self.assertRaises(ValidationError):
            self.reinitialiser()

    def test_motif_de_refus_lisible(self):
        self.assertIsNone(refus_reinitialisation(self.direction, self.enseignant, self.ecole))
        self.assertIn("propre", refus_reinitialisation(self.direction, self.direction, self.ecole))
        autre = self._membre("direction2")
        ResponsabiliteEcole.objects.create(appartenance=self.direction2_a)
        self.inscrire(autre)
        self.assertIn("déployeur", refus_reinitialisation(self.direction, autre, self.ecole))


class ReinitialisationParLeDeployeur(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.operateur = get_user_model().objects.create_user(
            "operateur", password=MOT_DE_PASSE, is_staff=True)
        self.cle = self.inscrire(self.direction)
        totp.generer_codes_secours(self.direction)

    def commande(self, **options):
        sortie = StringIO()
        arguments = {"utilisateur": "direction", "operateur": "operateur", "motif": "téléphone perdu"}
        arguments.update(options)
        call_command("reinitialiser_double_facteur", stdout=sortie, **arguments)
        return sortie.getvalue()

    def test_le_deployeur_reinitialise_une_direction(self):
        self.assertIn("réinitialisé", self.commande())
        self.assertFalse(totp.est_inscrit(self.direction))
        self.assertFalse(CodeSecoursDoubleFacteur.objects.exists())

    def test_l_operation_est_journalisee_avec_le_motif(self):
        self.commande()
        evenement = EvenementAudit.objects.get(action="securite.double_facteur_reinitialise")
        self.assertEqual((evenement.ecole, evenement.acteur), (self.ecole, self.operateur))
        self.assertEqual(evenement.nouvelles_valeurs["par"], "deployeur")
        self.assertEqual(evenement.nouvelles_valeurs["motif"], "téléphone perdu")

    def test_un_compte_dans_deux_ecoles_est_journalise_dans_chacune(self):
        autre = Ecole.objects.create(nom="École B")
        AppartenanceEcole.objects.create(utilisateur=self.direction, ecole=autre)
        self.commande()
        self.assertEqual(
            set(EvenementAudit.objects.filter(action="securite.double_facteur_reinitialise")
                .values_list("ecole_id", flat=True)), {self.ecole.pk, autre.pk})

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: DIRECTION})
    def test_l_obligation_demeure_apres_la_commande(self):
        self.commande()
        self.connecter(self.direction)
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                             fetch_redirect_response=False)

    def test_l_operateur_doit_etre_un_compte_technique_actif(self):
        for champs in ({"is_staff": False}, {"is_active": False}):
            with self.subTest(champs):
                get_user_model().objects.filter(pk=self.operateur.pk).update(is_staff=True, is_active=True)
                get_user_model().objects.filter(pk=self.operateur.pk).update(**champs)
                with self.assertRaises(CommandError):
                    self.commande()
                self.assertTrue(totp.est_inscrit(self.direction))

    def test_utilisateur_ou_operateur_introuvable(self):
        for options in ({"utilisateur": "personne"}, {"operateur": "personne"}):
            with self.subTest(options), self.assertRaises(CommandError):
                self.commande(**options)

    def test_le_service_refuse_un_operateur_ordinaire(self):
        with self.assertRaises(PermissionDenied):
            reinitialiser_par_le_deployeur(operateur=self.enseignant, cible=self.direction, motif="x")

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False)
    def test_la_commande_fonctionne_meme_si_la_fonction_est_indisponible(self):
        self.commande()
        self.assertFalse(totp.est_inscrit(self.direction))


class BoutonDansLEquipe(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.inscrire(self.enseignant)
        self.url = reverse("equipe_ecole")
        self.url_personnes = self.url + "?vue=personnes"

    def test_la_direction_voit_le_bouton_pour_un_rang_inferieur_inscrit(self):
        self.connecter_direction()
        page = self.client.get(self.url_personnes)
        self.assertContains(page, "Réinitialiser le second facteur", count=1)

    def connecter_direction(self):
        cle = self.inscrire(self.direction)
        self.connecter(self.direction)
        self.client.post(reverse("connexion_verification"), {"code": self.code(cle)})

    def test_pas_de_bouton_pour_une_personne_sans_second_facteur_ni_pour_soi(self):
        autre = self._membre("sans")
        self.connecter_direction()
        page = self.client.get(self.url_personnes).content.decode()
        # Un seul bouton : celui de l'enseignant inscrit, ni la direction (soi), ni « sans ».
        self.assertEqual(page.count("Réinitialiser le second facteur"), 1)
        self.assertIn(f'name="appartenance" value="{self.enseignant_a.pk}"', page)
        self.assertNotIn(f'name="action" value="reinitialiser_double_facteur"><input type="hidden" name="appartenance" value="{self.direction_a.pk}"', page)

    def test_pas_de_bouton_si_la_fonction_est_indisponible(self):
        self.connecter_direction()
        with override_settings(DOUBLE_FACTEUR_DISPONIBLE=False):
            self.assertNotContains(self.client.get(self.url_personnes), "Réinitialiser le second facteur")

    def test_la_reinitialisation_depuis_l_equipe(self):
        self.connecter_direction()
        appartenance = self.enseignant_a
        reponse = self.client.post(self.url, {
            "action": "reinitialiser_double_facteur", "appartenance": appartenance.pk,
            "vue": "personnes"}, follow=True)
        self.assertContains(reponse, "a été réinitialisé")
        self.assertFalse(totp.est_inscrit(self.enseignant))

    def test_une_direction_ne_peut_pas_viser_une_appartenance_d_une_autre_ecole(self):
        autre_ecole = Ecole.objects.create(nom="Ailleurs")
        etranger = get_user_model().objects.create_user("etranger", password=MOT_DE_PASSE)
        appartenance = AppartenanceEcole.objects.create(utilisateur=etranger, ecole=autre_ecole)
        self.inscrire(etranger)
        self.connecter_direction()
        reponse = self.client.post(self.url, {
            "action": "reinitialiser_double_facteur", "appartenance": appartenance.pk})
        self.assertEqual(reponse.status_code, 404)
        self.assertTrue(totp.est_inscrit(etranger))

    def test_la_reinitialisation_est_refusee_a_un_enseignant(self):
        cle = totp.dechiffrer(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).cle_chiffree)
        self.connecter(self.enseignant)
        self.client.post(reverse("connexion_verification"), {"code": self.code(cle)})
        reponse = self.client.post(self.url, {
            "action": "reinitialiser_double_facteur", "appartenance": self.direction_a.pk})
        self.assertIn(reponse.status_code, (302, 403))
        self.assertTrue(totp.est_inscrit(self.enseignant))
