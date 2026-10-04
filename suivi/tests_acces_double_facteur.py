"""Second facteur à la connexion, échéance d'inscription et inscription (#C8c)."""
import time
from datetime import timedelta
from importlib.util import find_spec
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from carnet.double_facteur import ASSOCIE, DIRECTION
from comptes import totp
from comptes.models import AffectationClasse, AppartenanceEcole, DoubleFacteurCompte, ResponsabiliteEcole
from comptes.tests_totp import cle_de_test, code_a

from .acces_double_facteur import SESSION_ATTENTE, SESSION_VERIFIE, poser_echeance_si_besoin
from .models import Classe, Ecole, PolitiqueDoubleFacteurEcole
from .services.equipe import creer_compte_et_accepter_invitation, inviter

DEPENDANCES = all(find_spec(n) is not None for n in ("cryptography", "qrcode", "django_otp"))
MOT_DE_PASSE = "École ! Rivière 2026 solide"
OBLIGATOIRE_DEPLOYEUR = "DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG"


def en_deux_facteurs(**supplementaires):
    return override_settings(
        DOUBLE_FACTEUR_DISPONIBLE=True, DOUBLE_FACTEUR_CLES=[cle_de_test()],
        DOUBLE_FACTEUR_CACHE_SECONDES=0, **supplementaires)


@skipUnless(DEPENDANCES, "requirements-2fa.txt non installé")
class BaseAcces(TestCase):
    def setUp(self):
        cache.clear()
        self.ecole = Ecole.objects.create(nom="École A")
        self.classe = Classe.objects.create(ecole=self.ecole, nom="A1")
        self.direction = self._membre("direction")
        ResponsabiliteEcole.objects.create(appartenance=self.direction_a)
        self.enseignant = self._membre("enseignant")
        AffectationClasse.objects.create(
            appartenance=self.enseignant_a, classe=self.classe, type=AffectationClasse.RESPONSABLE)
        self.classe.activer()
        self.client = Client()

    def _membre(self, nom):
        utilisateur = get_user_model().objects.create_user(
            nom, email=f"{nom}@example.test", password=MOT_DE_PASSE)
        appartenance = AppartenanceEcole.objects.create(utilisateur=utilisateur, ecole=self.ecole)
        setattr(self, f"{nom}_a", appartenance)
        return utilisateur

    def inscrire(self, utilisateur):
        """Inscription directe, avec un pas déjà consommé loin dans le passé."""
        compte = totp.commencer_inscription(utilisateur)
        cle = totp.cle_en_cours(compte)
        compte.confirme_le = timezone.now()
        compte.save(update_fields=["confirme_le"])
        return cle

    def code(self, cle):
        return code_a(cle, time.time())

    def connecter(self, utilisateur, client=None):
        client = client or self.client
        return client.post(reverse("connexion"), {
            "nom_utilisateur": utilisateur.username, "mot_de_passe": MOT_DE_PASSE})

    def est_connecte(self, client=None):
        return "_auth_user_id" in (client or self.client).session


class FonctionIndisponible(BaseAcces):
    def test_sans_la_fonction_la_connexion_ne_change_pas_meme_avec_une_ligne_inscrite(self):
        with en_deux_facteurs():
            cle = self.inscrire(self.enseignant)
        reponse = self.connecter(self.enseignant)
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertTrue(self.est_connecte())
        self.assertEqual(cle is not None, True)

    def test_page_d_inscription_introuvable(self):
        self.connecter(self.enseignant)
        self.assertEqual(self.client.get(reverse("double_facteur")).status_code, 404)


class ConnexionEnDeuxEtapes(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.cle = self.inscrire(self.enseignant)

    def test_aucune_session_n_est_ouverte_avant_le_second_facteur(self):
        reponse = self.connecter(self.enseignant)
        self.assertRedirects(reponse, reverse("connexion_verification"), fetch_redirect_response=False)
        self.assertFalse(self.est_connecte())
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("connexion"),
                             fetch_redirect_response=False)

    def test_code_valide_ouvre_la_session(self):
        self.connecter(self.enseignant)
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertTrue(self.est_connecte())
        self.assertTrue(self.client.session[SESSION_VERIFIE])
        self.assertNotIn(SESSION_ATTENTE, self.client.session)
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)

    def test_code_faux_n_ouvre_rien(self):
        self.connecter(self.enseignant)
        reponse = self.client.post(reverse("connexion_verification"), {"code": "000000"})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Code incorrect ou expiré")
        self.assertFalse(self.est_connecte())

    def test_un_code_deja_utilise_est_refuse(self):
        self.connecter(self.enseignant)
        code = self.code(self.cle)
        self.client.post(reverse("connexion_verification"), {"code": code})
        autre = Client()
        self.connecter(self.enseignant, autre)
        reponse = autre.post(reverse("connexion_verification"), {"code": code})
        self.assertFalse(self.est_connecte(autre))
        self.assertContains(reponse, "Code incorrect ou expiré")

    def test_mauvais_mot_de_passe_n_atteint_pas_le_second_facteur(self):
        reponse = self.client.post(reverse("connexion"), {
            "nom_utilisateur": "enseignant", "mot_de_passe": "faux"})
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn(SESSION_ATTENTE, self.client.session)

    def test_la_verification_sans_etape_prealable_renvoie_a_la_connexion(self):
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertRedirects(reponse, reverse("connexion"), fetch_redirect_response=False)
        self.assertFalse(self.est_connecte())

    def test_l_attente_expire(self):
        self.connecter(self.enseignant)
        session = self.client.session
        session[SESSION_ATTENTE]["jusqua"] = time.time() - 1
        session.save()
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertRedirects(reponse, reverse("connexion"), fetch_redirect_response=False)
        self.assertFalse(self.est_connecte())

    def test_revenir_a_la_connexion_annule_l_attente(self):
        self.connecter(self.enseignant)
        self.client.get(reverse("connexion"))
        self.assertNotIn(SESSION_ATTENTE, self.client.session)

    def test_compte_desactive_entre_temps(self):
        self.connecter(self.enseignant)
        self.enseignant.is_active = False
        self.enseignant.save()
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertRedirects(reponse, reverse("connexion"), fetch_redirect_response=False)

    @override_settings(RATELIMIT_DOUBLE_FACTEUR="3/15m", RATELIMIT_DOUBLE_FACTEUR_IP="100/15m")
    def test_les_saisies_sont_plafonnees_par_compte(self):
        self.connecter(self.enseignant)
        for _ in range(3):
            self.assertEqual(self.client.post(
                reverse("connexion_verification"), {"code": "000000"}).status_code, 200)
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertEqual(reponse.status_code, 429)
        self.assertFalse(self.est_connecte())
        # L'attente est abandonnée : il faut ressaisir le mot de passe.
        self.assertNotIn(SESSION_ATTENTE, self.client.session)

    @override_settings(RATELIMIT_DOUBLE_FACTEUR="100/15m", RATELIMIT_DOUBLE_FACTEUR_IP="2/15m")
    def test_les_saisies_sont_plafonnees_par_adresse(self):
        self.connecter(self.enseignant)
        for _ in range(2):
            self.client.post(reverse("connexion_verification"), {"code": "000000"})
        reponse = self.client.post(reverse("connexion_verification"), {"code": self.code(self.cle)})
        self.assertEqual(reponse.status_code, 429)

    def test_le_plafond_est_propre_a_chaque_compte(self):
        with override_settings(RATELIMIT_DOUBLE_FACTEUR="2/15m"):
            self.connecter(self.enseignant)
            for _ in range(3):
                self.client.post(reverse("connexion_verification"), {"code": "000000"})
            cle_direction = self.inscrire(self.direction)
            autre = Client()
            self.connecter(self.direction, autre)
            reponse = autre.post(reverse("connexion_verification"), {"code": self.code(cle_direction)})
            self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)

    def test_une_session_nee_sans_second_facteur_est_fermee(self):
        self.client.force_login(self.enseignant)
        reponse = self.client.get(reverse("accueil"))
        self.assertRedirects(reponse, reverse("connexion"), fetch_redirect_response=False)
        self.assertFalse(self.est_connecte())

    def test_fonction_desactivee_pas_de_second_facteur_demande(self):
        PolitiqueDoubleFacteurEcole.objects.create(ecole=self.ecole, desactive_a_partir_du_rang=2)
        reponse = self.connecter(self.enseignant)
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)
        self.assertTrue(self.est_connecte())

    def test_le_second_facteur_survit_a_une_reinitialisation_de_mot_de_passe(self):
        self.enseignant.set_password("Nouveau ! Mot 2026 de passe")
        self.enseignant.save()
        reponse = self.client.post(reverse("connexion"), {
            "nom_utilisateur": "enseignant", "mot_de_passe": "Nouveau ! Mot 2026 de passe"})
        self.assertRedirects(reponse, reverse("connexion_verification"), fetch_redirect_response=False)
        self.assertFalse(self.est_connecte())


class EcheanceDInscription(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE, "DOUBLE_FACTEUR_DELAI_GRACE_JOURS": 14})
        reglage.enable()
        self.addCleanup(reglage.disable)

    def test_premier_constat_pose_une_echeance_et_affiche_le_rappel(self):
        self.connecter(self.enseignant)
        reponse = self.client.get(reverse("accueil"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "il vous reste 14 jours")
        echeance = DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le
        self.assertAlmostEqual((echeance - timezone.now()).total_seconds(), 14 * 86400, delta=60)

    def test_l_echeance_ne_se_repousse_pas(self):
        self.connecter(self.enseignant)
        self.client.get(reverse("accueil"))
        premiere = DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le
        self.client.get(reverse("accueil"))
        self.assertEqual(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le, premiere)

    def test_apres_l_echeance_l_acces_est_bloque_sauf_inscription_et_deconnexion(self):
        self.connecter(self.enseignant)
        self.client.get(reverse("accueil"))
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(
            echeance_le=timezone.now() - timedelta(seconds=1))
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("mon_compte")), reverse("double_facteur"),
                             fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("double_facteur")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("deconnexion")), reverse("connexion"),
                             fetch_redirect_response=False)

    @override_settings(DOUBLE_FACTEUR_DELAI_GRACE_JOURS=0)
    def test_sans_delai_de_grace_le_blocage_est_immediat(self):
        self.connecter(self.enseignant)
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                             fetch_redirect_response=False)

    def test_les_fonctions_non_concernees_ne_sont_pas_touchees(self):
        contributeur = self._membre("contributeur")
        AffectationClasse.objects.create(
            appartenance=self.contributeur_a, classe=self.classe, type=AffectationClasse.CONTRIBUTEUR)
        self.connecter(contributeur)
        reponse = self.client.get(reverse("accueil"))
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "il vous reste")
        self.assertFalse(DoubleFacteurCompte.objects.filter(utilisateur=contributeur).exists())

    def test_les_rangs_superieurs_sont_aussi_concernes(self):
        self.connecter(self.direction)
        self.assertContains(self.client.get(reverse("accueil")), "il vous reste 14 jours")

    def test_devenir_optionnel_efface_l_echeance(self):
        self.connecter(self.enseignant)
        self.client.get(reverse("accueil"))
        with override_settings(**{OBLIGATOIRE_DEPLOYEUR: 0}):
            self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)
        self.assertIsNone(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le)

    def test_redevenir_obligatoire_donne_un_nouveau_delai(self):
        self.connecter(self.enseignant)
        self.client.get(reverse("accueil"))
        with override_settings(**{OBLIGATOIRE_DEPLOYEUR: 0}):
            self.client.get(reverse("accueil"))
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(echeance_le=None)
        reponse = self.client.get(reverse("accueil"))
        self.assertContains(reponse, "il vous reste 14 jours")

    def test_l_exigence_est_conservee_en_session_pendant_la_duree_du_cache(self):
        self.connecter(self.enseignant)
        with override_settings(DOUBLE_FACTEUR_CACHE_SECONDES=60):
            self.client.get(reverse("accueil"))
            with override_settings(**{OBLIGATOIRE_DEPLOYEUR: 0}):
                self.client.get(reverse("accueil"))
            self.assertIsNotNone(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le)

    def test_compte_neuf_par_invitation_sans_delai_de_grace(self):
        invitation, jeton = inviter(utilisateur=self.direction, ecole=self.ecole, email="neuf@example.test")
        AffectationClasse.objects.create(
            invitation=invitation, classe=self.classe, type=AffectationClasse.ENSEIGNANT_ASSOCIE)
        neuf = creer_compte_et_accepter_invitation(
            invitation=invitation, jeton=jeton, username="neuf", first_name="Neu", last_name="F",
            password=MOT_DE_PASSE)
        echeance = DoubleFacteurCompte.objects.get(utilisateur=neuf).echeance_le
        self.assertLessEqual(echeance, timezone.now())
        self.connecter(neuf)
        self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                             fetch_redirect_response=False)

    def test_compte_neuf_non_concerne_n_a_aucune_ligne(self):
        invitation, jeton = inviter(utilisateur=self.direction, ecole=self.ecole, email="libre@example.test")
        AffectationClasse.objects.create(
            invitation=invitation, classe=self.classe, type=AffectationClasse.CONTRIBUTEUR)
        libre = creer_compte_et_accepter_invitation(
            invitation=invitation, jeton=jeton, username="libre", first_name="Li", last_name="Bre",
            password=MOT_DE_PASSE)
        self.assertFalse(DoubleFacteurCompte.objects.filter(utilisateur=libre).exists())

    def test_poser_echeance_ne_fait_rien_sans_la_fonction(self):
        with override_settings(DOUBLE_FACTEUR_DISPONIBLE=False):
            poser_echeance_si_besoin(self.enseignant)
        self.assertFalse(DoubleFacteurCompte.objects.exists())


class InscriptionEtRetrait(BaseAcces):
    def setUp(self):
        super().setUp()
        reglage = en_deux_facteurs()
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.connecter(self.enseignant)

    def lire_cle(self, reponse):
        compte = DoubleFacteurCompte.objects.get(utilisateur=self.enseignant)
        return totp.cle_en_cours(compte)

    def test_mon_compte_propose_la_configuration(self):
        self.assertContains(self.client.get(reverse("mon_compte")), reverse("double_facteur"))

    def test_page_d_inscription_montre_le_qr_et_la_cle_une_seule_fois(self):
        reponse = self.client.get(reverse("double_facteur"))
        cle = self.lire_cle(reponse)
        self.assertContains(reponse, "<svg")
        self.assertContains(reponse, " ".join(totp.cle_en_base32(cle)[i:i + 4] for i in range(0, 32, 4)))
        self.assertEqual(reponse["Cache-Control"].split(",")[0].strip().lower() in ("max-age=0", "no-cache", "no-store"), True)
        # Même clé au rechargement tant que ce n'est pas confirmé.
        self.assertEqual(self.lire_cle(self.client.get(reverse("double_facteur"))), cle)

    def test_inscription_par_un_code_valide(self):
        cle = self.lire_cle(self.client.get(reverse("double_facteur")))
        reponse = self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        self.assertRedirects(reponse, reverse("mon_compte"), fetch_redirect_response=False)
        self.assertTrue(totp.est_inscrit(self.enseignant))
        self.assertTrue(self.client.session[SESSION_VERIFIE])
        self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)
        page = self.client.get(reverse("double_facteur"))
        self.assertNotContains(page, "<svg")
        self.assertContains(page, "Retirer le second facteur")

    def test_inscription_par_un_code_faux(self):
        self.client.get(reverse("double_facteur"))
        reponse = self.client.post(reverse("double_facteur"), {"code": "000000"})
        self.assertContains(reponse, "Code incorrect ou expiré")
        self.assertFalse(totp.est_inscrit(self.enseignant))

    def test_la_cle_n_apparait_jamais_dans_la_reponse_une_fois_inscrit(self):
        cle = self.lire_cle(self.client.get(reverse("double_facteur")))
        self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        for nom in ("double_facteur", "mon_compte"):
            page = self.client.get(reverse(nom)).content.decode()
            self.assertNotIn(totp.cle_en_base32(cle), page)

    def test_retrait_volontaire_exige_un_code(self):
        cle = self.lire_cle(self.client.get(reverse("double_facteur")))
        self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        reponse = self.client.post(reverse("double_facteur"), {"action": "retirer", "code": "000000"})
        self.assertContains(reponse, "Code incorrect ou expiré")
        self.assertTrue(totp.est_inscrit(self.enseignant))
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(dernier_pas=0)
        reponse = self.client.post(reverse("double_facteur"), {"action": "retirer", "code": self.code(cle)})
        self.assertRedirects(reponse, reverse("mon_compte"), fetch_redirect_response=False)
        self.assertFalse(totp.est_inscrit(self.enseignant))

    def test_retrait_refuse_si_le_second_facteur_est_obligatoire(self):
        cle = self.lire_cle(self.client.get(reverse("double_facteur")))
        self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(dernier_pas=0)
        with override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE}):
            reponse = self.client.post(reverse("double_facteur"), {"action": "retirer", "code": self.code(cle)})
            self.assertContains(reponse, "obligatoire pour votre fonction")
            self.assertTrue(totp.est_inscrit(self.enseignant))
            self.assertNotContains(self.client.get(reverse("double_facteur")), "Retirer le second facteur")

    def test_apres_le_retrait_la_connexion_ne_demande_plus_de_code(self):
        cle = self.lire_cle(self.client.get(reverse("double_facteur")))
        self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
        DoubleFacteurCompte.objects.filter(utilisateur=self.enseignant).update(dernier_pas=0)
        self.client.post(reverse("double_facteur"), {"action": "retirer", "code": self.code(cle)})
        autre = Client()
        reponse = self.connecter(self.enseignant, autre)
        self.assertRedirects(reponse, reverse("accueil"), fetch_redirect_response=False)

    def test_inscription_apres_echeance_leve_le_blocage(self):
        with override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE, "DOUBLE_FACTEUR_DELAI_GRACE_JOURS": 0}):
            self.assertRedirects(self.client.get(reverse("accueil")), reverse("double_facteur"),
                                 fetch_redirect_response=False)
            cle = self.lire_cle(self.client.get(reverse("double_facteur")))
            self.client.post(reverse("double_facteur"), {"code": self.code(cle)})
            self.assertEqual(self.client.get(reverse("accueil")).status_code, 200)
            self.assertIsNone(DoubleFacteurCompte.objects.get(utilisateur=self.enseignant).echeance_le)

    @override_settings(RATELIMIT_DOUBLE_FACTEUR="2/15m")
    def test_saisies_d_inscription_plafonnees(self):
        self.client.get(reverse("double_facteur"))
        for _ in range(2):
            self.client.post(reverse("double_facteur"), {"code": "000000"})
        self.assertEqual(self.client.post(reverse("double_facteur"), {"code": "000000"}).status_code, 429)

    def test_fonction_desactivee_page_introuvable_pour_un_compte_non_inscrit(self):
        PolitiqueDoubleFacteurEcole.objects.create(ecole=self.ecole, desactive_a_partir_du_rang=2)
        self.assertEqual(self.client.get(reverse("double_facteur")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("mon_compte")), reverse("double_facteur"))

    def test_page_reservee_aux_comptes_connectes(self):
        self.client.get(reverse("deconnexion"))
        self.assertRedirects(self.client.get(reverse("double_facteur")), reverse("connexion"),
                             fetch_redirect_response=False)
