from datetime import timedelta
from importlib.util import find_spec
from unittest import skipUnless

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from io import StringIO

from carnet.reseau import adresse_client

from .tests import Base, TestCase


def requete(distante="10.0.0.1", transmis=None):
    extra = {"REMOTE_ADDR": distante}
    if transmis is not None:
        extra["HTTP_X_FORWARDED_FOR"] = transmis
    return RequestFactory().get("/", **extra)


class AdresseClient(SimpleTestCase):
    @override_settings(PROXYS_DE_CONFIANCE=0)
    def test_par_defaut_l_en_tete_transmis_est_ignore(self):
        self.assertEqual(
            adresse_client(requete(transmis="203.0.113.9")), "10.0.0.1"
        )

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_un_proxy_la_derniere_entree_est_le_client(self):
        self.assertEqual(
            adresse_client(requete(transmis="203.0.113.9")), "203.0.113.9"
        )

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_les_entrees_forgees_a_gauche_sont_ignorees(self):
        self.assertEqual(
            adresse_client(requete(transmis="1.2.3.4, 5.6.7.8, 203.0.113.9")),
            "203.0.113.9",
        )

    @override_settings(PROXYS_DE_CONFIANCE=2)
    def test_deux_proxys_l_avant_derniere_entree_est_le_client(self):
        self.assertEqual(
            adresse_client(requete(transmis="1.2.3.4, 203.0.113.9, 198.51.100.7")),
            "203.0.113.9",
        )

    @override_settings(PROXYS_DE_CONFIANCE=2)
    def test_un_n_trop_grand_expose_une_entree_forgeable(self):
        # Un seul proxy réel, mais N=2 : le client préfixe l'en-tête et
        # impose l'adresse retenue. Ce test documente le danger d'un N trop
        # grand (voir DEPLOIEMENT.org), il n'en fait pas un comportement voulu.
        self.assertEqual(
            adresse_client(requete(transmis="192.0.2.66, 203.0.113.9")),
            "192.0.2.66",
        )

    @override_settings(PROXYS_DE_CONFIANCE=2)
    def test_un_en_tete_trop_court_retombe_sur_l_adresse_directe(self):
        self.assertEqual(
            adresse_client(requete(transmis="203.0.113.9")), "10.0.0.1"
        )

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_l_absence_d_en_tete_retombe_sur_l_adresse_directe(self):
        self.assertEqual(adresse_client(requete()), "10.0.0.1")

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_une_valeur_qui_n_est_pas_une_adresse_retombe_sur_l_adresse_directe(self):
        for valeur in ("pas-une-adresse", "", "203.0.113.9:4711"):
            with self.subTest(valeur=valeur):
                self.assertEqual(
                    adresse_client(requete(transmis=valeur)), "10.0.0.1"
                )

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_ipv6_est_normalisee(self):
        self.assertEqual(
            adresse_client(requete(transmis="2001:DB8:0:0:0:0:0:1")),
            "2001:db8::1",
        )


class ProtectionsDerriereUnProxy(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def connexion_depuis(self, client_reel, mdp):
        return self.client.post(
            reverse("connexion"),
            {"nom_utilisateur": self.enseignant.username, "mot_de_passe": mdp},
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR=client_reel,
        )

    @skipUnless(find_spec("axes") is not None, "django-axes absent")
    @override_settings(
        PROXYS_DE_CONFIANCE=1,
        AXES_FAILURE_LIMIT=3,
        AXES_COOLOFF_TIME=timedelta(minutes=15),
    )
    def test_le_blocage_ne_touche_que_l_adresse_fautive(self):
        for _ in range(3):
            self.connexion_depuis("203.0.113.9", "mauvais-mot-de-passe")
        bloque = self.connexion_depuis("203.0.113.9", "ens-mdp")
        self.assertEqual(bloque.status_code, 429)

        # Une autre personne, derrière le même proxy, n'est pas bloquée.
        self.connexion_depuis("198.51.100.7", "ens-mdp")
        self.assertEqual(
            self.client.session["_auth_user_id"], str(self.enseignant.pk)
        )

    @skipUnless(find_spec("axes") is not None, "django-axes absent")
    @override_settings(
        PROXYS_DE_CONFIANCE=0,
        AXES_FAILURE_LIMIT=3,
        AXES_COOLOFF_TIME=timedelta(minutes=15),
    )
    def test_sans_reglage_le_blocage_reste_celui_de_l_adresse_du_proxy(self):
        for adresse in ("203.0.113.9", "203.0.113.10", "203.0.113.11"):
            self.connexion_depuis(adresse, "mauvais-mot-de-passe")
        reponse = self.connexion_depuis("198.51.100.7", "ens-mdp")
        self.assertEqual(reponse.status_code, 429)

    @skipUnless(find_spec("axes") is not None, "django-axes absent")
    @override_settings(
        PROXYS_DE_CONFIANCE=1,
        AXES_FAILURE_LIMIT=3,
        AXES_COOLOFF_TIME=timedelta(minutes=15),
    )
    def test_un_en_tete_forge_ne_contourne_pas_le_blocage(self):
        for i in range(3):
            self.connexion_depuis(
                f"192.0.2.{i}, 203.0.113.9", "mauvais-mot-de-passe"
            )
        reponse = self.connexion_depuis("192.0.2.99, 203.0.113.9", "ens-mdp")
        self.assertEqual(reponse.status_code, 429)

    def demander(self, client_reel):
        return self.client.post(
            reverse("mot_de_passe_oublie"),
            {"email": "inconnue@example.test"},
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR=client_reel,
            follow=True,
        )

    @override_settings(PROXYS_DE_CONFIANCE=1, RATELIMIT_MOT_DE_PASSE_OUBLIE="2/h")
    def test_le_plafond_du_mot_de_passe_oublie_est_par_client(self):
        for _ in range(2):
            self.demander("203.0.113.9")
        self.assertContains(self.demander("203.0.113.9"), "Trop de demandes")
        self.assertNotContains(self.demander("198.51.100.7"), "Trop de demandes")

    @override_settings(PROXYS_DE_CONFIANCE=0, RATELIMIT_MOT_DE_PASSE_OUBLIE="2/h")
    def test_sans_reglage_le_plafond_reste_commun_derriere_un_proxy(self):
        for _ in range(2):
            self.demander("203.0.113.9")
        self.assertContains(self.demander("198.51.100.7"), "Trop de demandes")

    @override_settings(PROXYS_DE_CONFIANCE=1)
    def test_le_journal_des_echecs_porte_l_adresse_du_client(self):
        with self.assertLogs("suivi.views", level="WARNING") as journal:
            self.connexion_depuis("203.0.113.9", "mauvais-mot-de-passe")
        self.assertIn("depuis 203.0.113.9", "\n".join(journal.output))


class DiagnosticAdresseClient(TestCase):
    @override_settings(
        PROXYS_DE_CONFIANCE=0,
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_avertit_sans_echouer_quand_https_est_force_sans_proxy_declare(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn("Adresse IP des clients : adresse directe", texte)
        self.assertIn("CARNET_PROXYS_NB", texte)

    @override_settings(PROXYS_DE_CONFIANCE=0, SECURE_SSL_REDIRECT=False)
    def test_pas_d_avertissement_sans_https_force(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        self.assertNotIn("CARNET_PROXYS_NB", sortie.getvalue())

    @override_settings(
        PROXYS_DE_CONFIANCE=1,
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
    )
    def test_indique_le_nombre_de_proxys(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn("derrière 1 proxy(s) de confiance", texte)
        self.assertNotIn("CARNET_PROXYS_NB", texte)


class DiagnosticExpediteur(TestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_DISPONIBLE=True,
        DEFAULT_FROM_EMAIL="Petits Pas <ne-pas-repondre@petits-pas.example>",
    )
    def test_avertit_quand_l_expediteur_est_fictif(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        self.assertIn("CARNET_EMAIL_EXPEDITEUR", sortie.getvalue())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_DISPONIBLE=True,
        DEFAULT_FROM_EMAIL="Petits Pas <ne-pas-repondre@ecole.example.org>",
    )
    def test_pas_d_avertissement_avec_un_expediteur_reel(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        self.assertNotIn("CARNET_EMAIL_EXPEDITEUR", sortie.getvalue())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DISPONIBLE=True,
        DEFAULT_FROM_EMAIL="Petits Pas <ne-pas-repondre@petits-pas.example>",
    )
    def test_pas_d_avertissement_hors_smtp(self):
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        self.assertNotIn("CARNET_EMAIL_EXPEDITEUR", sortie.getvalue())
