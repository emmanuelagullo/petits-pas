"""Écran de politique de 2FA de l'école et diagnostic de déploiement (#C8e)."""
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from carnet.double_facteur import ASSOCIE, CONTRIBUTEUR, DIRECTION, RESPONSABLE, SANS_FONCTION
from comptes import totp
from comptes.models import AffectationClasse
from comptes.tests_totp import cle_de_test

from .double_facteur import Exigence, apercu_ecole, exigence_double_facteur
from .models import EvenementAudit, PolitiqueDoubleFacteurEcole
from .tests_acces_double_facteur import OBLIGATOIRE_DEPLOYEUR, BaseAcces, en_deux_facteurs

DESACTIVE_DEPLOYEUR = "DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG"


class BaseEcran(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.url = reverse("double_facteur_ecole")

    def connecter_direction(self):
        self.connecter(self.direction)

    def enregistrer(self, obligatoire, desactive, revision=0, **extra):
        return self.client.post(self.url, {
            "obligatoire": obligatoire, "desactive": desactive, "revision": revision, **extra})


class EcranDePolitique(BaseEcran):
    def test_la_direction_voit_l_ecran_avec_les_valeurs_par_defaut(self):
        self.connecter_direction()
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Personne n'est soumis à l'obligation")
        self.assertNotContains(page, "Cadre fixé par l'hébergeur")
        self.assertContains(page, 'name="revision" value="0"')

    def test_enregistrement_et_effet_immediat_sur_les_membres(self):
        self.connecter_direction()
        reponse = self.enregistrer(RESPONSABLE, 6)
        self.assertRedirects(reponse, self.url, fetch_redirect_response=False)
        politique = PolitiqueDoubleFacteurEcole.objects.get(ecole=self.ecole)
        self.assertEqual((politique.obligatoire_jusqu_au_rang, politique.desactive_a_partir_du_rang), (2, 6))
        self.assertEqual(exigence_double_facteur(self.enseignant), Exigence.OBLIGATOIRE)
        self.assertTrue(EvenementAudit.objects.filter(action="securite.double_facteur_ecole").exists())
        page = self.client.get(self.url)
        self.assertContains(page, "2 personnes soumises à l'obligation, dont 0 déjà inscrite")
        self.assertContains(page, "a été enregistrée")

    def test_les_valeurs_enregistrees_sont_preselectionnees(self):
        self.connecter_direction()
        self.enregistrer(ASSOCIE, CONTRIBUTEUR)
        page = self.client.get(self.url).content.decode()
        self.assertRegex(page, r'name="obligatoire" value="3"\s+checked')
        self.assertRegex(page, r'name="desactive" value="4"\s+checked')
        self.assertContains(self.client.get(self.url), 'name="revision" value="1"')

    def test_apercu_compte_les_inscrits(self):
        self.connecter_direction()
        self.inscrire(self.enseignant)
        self.enregistrer(RESPONSABLE, 6)
        page = self.client.get(self.url)
        self.assertContains(page, "dont 1 déjà inscrite")
        self.assertEqual(apercu_ecole(self.ecole)["concernes"], 2)

    def test_revision_perimee_refusee_et_choix_conserves(self):
        self.connecter_direction()
        self.enregistrer(RESPONSABLE, 6)
        reponse = self.enregistrer(ASSOCIE, 6, revision=0)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "a changé depuis sa consultation")
        self.assertRegex(reponse.content.decode(), r'name="obligatoire" value="3"\s+checked')
        self.assertEqual(PolitiqueDoubleFacteurEcole.objects.get().obligatoire_jusqu_au_rang, 2)

    def test_valeurs_incoherentes_ou_absentes_refusees(self):
        self.connecter_direction()
        for obligatoire, desactive in [(4, 3), (3, 3), ("x", 6), (2, ""), ("", ""), (9, 6)]:
            with self.subTest((obligatoire, desactive)):
                reponse = self.enregistrer(obligatoire, desactive)
                self.assertEqual(reponse.status_code, 200)
                self.assertContains(reponse, 'role="alert"')
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    def test_reservee_a_la_direction(self):
        self.connecter(self.enseignant)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.enregistrer(1, 6).status_code, 403)
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    def test_page_reservee_aux_comptes_connectes(self):
        self.assertRedirects(self.client.get(self.url), reverse("connexion"),
                             fetch_redirect_response=False)

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False)
    def test_introuvable_si_la_fonction_est_indisponible(self):
        self.connecter_direction()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.enregistrer(1, 6).status_code, 404)
        self.assertNotContains(self.client.get(reverse("gestion")), self.url)

    def test_lien_depuis_la_page_de_gestion(self):
        self.connecter_direction()
        self.assertContains(self.client.get(reverse("gestion")), self.url)


class EcranSousLeCadreDeLHebergeur(BaseEcran):
    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: RESPONSABLE})
    def test_le_cadre_de_l_hebergeur_est_affiche_et_ses_choix_verrouilles(self):
        self.connecter_direction()
        page = self.client.get(self.url)
        self.assertContains(page, "Cadre fixé par l'hébergeur")
        contenu = page.content.decode()
        # Impossible de retirer le 2FA aux rangs que l'hébergeur impose.
        for rang in (1, 2):
            self.assertRegex(contenu, rf'name="desactive" value="{rang}"[^>]*disabled')
        self.assertNotRegex(contenu, r'name="desactive" value="3"[^>]*disabled')
        self.assertNotRegex(contenu, r'name="obligatoire" value="3"[^>]*disabled')

    @override_settings(**{DESACTIVE_DEPLOYEUR: CONTRIBUTEUR})
    def test_on_ne_peut_pas_exiger_ce_que_l_hebergeur_retire(self):
        self.connecter_direction()
        contenu = self.client.get(self.url).content.decode()
        for rang in (4, 5):
            self.assertRegex(contenu, rf'name="obligatoire" value="{rang}"[^>]*disabled')
        reponse = self.enregistrer(CONTRIBUTEUR, 6)
        self.assertContains(reponse, "ce que le déployeur a désactivé")
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_on_ne_peut_pas_retirer_ce_que_l_hebergeur_impose(self):
        self.connecter_direction()
        reponse = self.enregistrer(0, ASSOCIE)
        self.assertContains(reponse, "ce que le déployeur a rendu obligatoire")
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_une_valeur_moins_stricte_que_l_hebergeur_est_acceptee_sans_effet(self):
        self.connecter_direction()
        self.enregistrer(RESPONSABLE, 6)
        self.assertEqual(exigence_double_facteur(self.enseignant), Exigence.OBLIGATOIRE)
        self.assertEqual(exigence_double_facteur(self.direction), Exigence.OBLIGATOIRE)

    @override_settings(**{DESACTIVE_DEPLOYEUR: CONTRIBUTEUR})
    def test_un_avertissement_signale_une_politique_devenue_incompatible(self):
        PolitiqueDoubleFacteurEcole.objects.create(
            ecole=self.ecole, obligatoire_jusqu_au_rang=SANS_FONCTION, desactive_a_partir_du_rang=6)
        self.connecter_direction()
        self.assertContains(self.client.get(self.url), "sans effet")


class DiagnosticDeploiement(BaseAcces):
    def diagnostic(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        return sortie.getvalue()

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False, DOUBLE_FACTEUR_DEPENDANCES=False, MODE_LOCAL=False)
    def test_sans_dependances(self):
        self.assertIn("absent (dépendances de requirements-2fa.txt non installées)", self.diagnostic())

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False, DOUBLE_FACTEUR_DEPENDANCES=True, MODE_LOCAL=False)
    def test_sans_cle(self):
        self.assertIn("absent (CARNET_2FA_CLE non renseignée)", self.diagnostic())

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False, MODE_LOCAL=True)
    def test_mode_local(self):
        self.assertIn("indisponible (mode local)", self.diagnostic())

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False, DOUBLE_FACTEUR_DEPENDANCES=False, MODE_LOCAL=False)
    def test_une_obligation_d_ecole_sans_effet_est_signalee_sans_echec(self):
        PolitiqueDoubleFacteurEcole.objects.create(
            ecole=self.ecole, obligatoire_jusqu_au_rang=2, desactive_a_partir_du_rang=6)
        sortie = self.diagnostic()
        self.assertIn("1 école(s) ont posé une obligation", sortie)

    def test_fonction_disponible_decrit_la_politique_sans_reveler_de_cle(self):
        cle = cle_de_test()
        with en_deux_facteurs(**{OBLIGATOIRE_DEPLOYEUR: RESPONSABLE, DESACTIVE_DEPLOYEUR: SANS_FONCTION}):
            with override_settings(DOUBLE_FACTEUR_CLES=[cle], DOUBLE_FACTEUR_DELAI_GRACE_JOURS=7):
                sortie = self.diagnostic()
        self.assertIn("disponible", sortie)
        self.assertIn("Obligatoire jusqu'au rang 2 (responsable), délai de grâce 7 jour(s)", sortie)
        self.assertIn("Retiré à partir du rang 5 (sans_fonction)", sortie)
        self.assertIn("Clés de chiffrement : 1", sortie)
        self.assertNotIn(cle, sortie)

    def test_plusieurs_cles_signalent_une_rotation(self):
        with en_deux_facteurs():
            with override_settings(DOUBLE_FACTEUR_CLES=[cle_de_test(), cle_de_test()]):
                self.assertIn("une rotation est en cours", self.diagnostic())

    @override_settings(DOUBLE_FACTEUR_DISPONIBLE=False, DOUBLE_FACTEUR_DEPENDANCES=False, MODE_LOCAL=False)
    def test_le_diagnostic_ne_leve_aucune_erreur_sans_la_fonction(self):
        self.diagnostic()
