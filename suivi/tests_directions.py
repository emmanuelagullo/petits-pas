"""Gestion à plusieurs, passations, dates, isolement et droits pédagogiques."""
from datetime import timedelta
from io import StringIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone

from comptes.models import AppartenanceEcole, ResponsabiliteEcole, Utilisateur, DoubleFacteurCompte
from suivi.autorisations import autorise, VOIR_SUIVI, ADMINISTRER_ECOLE
from suivi.models import Ecole, Classe, EvenementAudit
from suivi.services.equipe import attribuer_direction, terminer_direction

MDP = "Une phrase secrète de test 2026 !"


class Directions(TestCase):
    def setUp(self):
        self.ecole = Ecole.objects.create(nom="École fictive")
        self.classe = Classe.objects.create(ecole=self.ecole, nom="Classe fictive")
        self.a, self.ma = self.membre("a")
        self.b, self.mb = self.membre("b")
        self.ra = ResponsabiliteEcole.objects.create(appartenance=self.ma)
        self.url = reverse("equipe_ecole")
        self.client.force_login(self.a)

    def membre(self, nom, ecole=None):
        u = Utilisateur.objects.create_user(nom, password=MDP, email=f"{nom}@example.test")
        return u, AppartenanceEcole.objects.create(utilisateur=u, ecole=ecole or self.ecole)

    def accorder(self, **kwargs):
        return attribuer_direction(utilisateur=self.a, appartenance=self.mb, **kwargs)

    def post(self, action="accorder_gestion", **kwargs):
        return self.client.post(self.url, {"action": action, "appartenance": self.mb.pk,
            "mot_de_passe": MDP, **kwargs}, follow=True)

    def test_deux_directions_et_pas_de_suivi_implicite(self):
        self.post()
        self.assertTrue(autorise(self.b, ADMINISTRER_ECOLE, self.ecole))
        self.assertFalse(autorise(self.b, VOIR_SUIVI, self.classe))
        self.assertTrue(EvenementAudit.objects.filter(action="direction.attribuee", acteur=self.a).exists())

    def test_confirmation_obligatoire_et_date_validee(self):
        for champs in ({"mot_de_passe": "faux"}, {"date_fin": "invalide"},
                       {"date_fin": (timezone.localdate() - timedelta(days=1)).isoformat()}):
            self.post(**champs)
            self.assertFalse(ResponsabiliteEcole.objects.filter(appartenance=self.mb).exists())

    def test_isolement_et_non_direction(self):
        autre = Ecole.objects.create(nom="Autre école")
        u, m = self.membre("autre", autre)
        self.assertEqual(self.client.post(self.url, {"action": "accorder_gestion",
            "appartenance": m.pk, "mot_de_passe": MDP}).status_code, 404)
        with self.assertRaises(PermissionDenied):
            attribuer_direction(utilisateur=self.a, appartenance=m)
        self.client.force_login(self.b)
        self.client.post(self.url, {"action": "accorder_gestion", "appartenance": self.mb.pk, "mot_de_passe": MDP})
        self.assertFalse(ResponsabiliteEcole.objects.filter(appartenance=self.mb).exists())

    def test_passation_et_retrait_de_soi(self):
        self.accorder()
        page = self.post("retirer_gestion", responsabilite=self.ra.pk)
        self.ra.refresh_from_db()
        self.assertEqual(self.ra.etat, "terminee")
        self.assertFalse(autorise(self.a, ADMINISTRER_ECOLE, self.ecole))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(EvenementAudit.objects.filter(action="direction.terminee").exists())

    def test_derniere_direction_et_double_retrait_refuses(self):
        with self.assertRaises(ValidationError):
            terminer_direction(utilisateur=self.a, responsabilite=self.ra)
        rb = self.accorder()
        terminer_direction(utilisateur=self.a, responsabilite=rb)
        with self.assertRaises(ValidationError):
            terminer_direction(utilisateur=self.a, responsabilite=rb)

    def test_remplacement_temporaire_ne_permet_pas_le_depart_definitif(self):
        self.accorder(date_fin=timezone.localdate() + timedelta(days=7))
        with self.assertRaises(ValidationError):
            terminer_direction(utilisateur=self.a, responsabilite=self.ra)

    def test_fin_appartenance_limite_les_droits(self):
        self.mb.date_fin = timezone.localdate() + timedelta(days=7)
        self.mb.save()
        with self.assertRaises(ValidationError):
            self.accorder()
        self.accorder(date_fin=self.mb.date_fin)
        with self.assertRaises(ValidationError):
            terminer_direction(utilisateur=self.a, responsabilite=self.ra)

    def test_compte_et_appartenance_derniere_direction_proteges(self):
        self.a.is_active = False
        with self.assertRaises(ValidationError):
            self.a.save(update_fields=["is_active"])
        self.a.is_active = True
        for champ, valeur in (("etat", "terminee"), ("date_fin", timezone.localdate() + timedelta(days=1))):
            setattr(self.ma, champ, valeur)
            with self.assertRaises(ValidationError):
                self.ma.save(update_fields=[champ])
            self.ma.refresh_from_db()
        self.ra.date_fin = timezone.localdate() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.ra.save()

    def test_compte_direction_peut_etre_desactive_si_releve(self):
        self.accorder()
        self.a.is_active = False
        self.a.save(update_fields=["is_active"])
        self.assertFalse(Utilisateur.objects.get(pk=self.a.pk).is_active)

    def test_badge_expire_et_alerte_sur_ancienne_configuration(self):
        self.accorder(date_fin=timezone.localdate())
        ResponsabiliteEcole.objects.filter(appartenance=self.mb).update(date_fin=timezone.localdate() - timedelta(days=1))
        page = self.client.get(self.url + "?vue=personnes")
        self.assertEqual(page.content.decode().count('<span class="pastille">Direction</span>'), 1)
        ResponsabiliteEcole.objects.filter(pk=self.ra.pk).update(date_fin=timezone.localdate())
        self.assertContains(self.client.get(self.url), "sans interruption ni fin prévue")

    def test_releve_future_continue_et_trou_refuse(self):
        jour = timezone.localdate()
        self.ra.date_fin = jour + timedelta(days=2)
        ResponsabiliteEcole.objects.create(appartenance=self.mb, date_debut=jour + timedelta(days=3))
        self.ra.save()
        from suivi.continuite_direction import verifier_continuite_direction
        verifier_continuite_direction(self.ecole.pk)
        ResponsabiliteEcole.objects.filter(appartenance=self.mb).update(date_debut=jour + timedelta(days=4))
        with self.assertRaises(ValidationError):
            verifier_continuite_direction(self.ecole.pk)

    def test_diagnostic_signale_une_perte_de_gouvernance(self):
        ResponsabiliteEcole.objects.filter(pk=self.ra.pk).update(date_fin=timezone.localdate())
        sortie = StringIO()
        call_command("diagnostiquer_deploiement", stdout=sortie)
        self.assertIn("relève absente ou droits avec fin prévue", sortie.getvalue())

    def test_etat_inactif_et_doublon_refuses(self):
        self.mb.etat = "terminee"
        self.mb.save()
        with self.assertRaises(ValidationError):
            self.accorder()
        self.mb.etat = "active"
        self.mb.save()
        self.accorder()
        with self.assertRaises(ValidationError):
            self.accorder()

    def test_csrf_exige_pour_les_droits(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        self.assertEqual(client.post(self.url, {"action": "accorder_gestion",
            "appartenance": self.mb.pk, "mot_de_passe": MDP}).status_code, 403)
        self.assertFalse(ResponsabiliteEcole.objects.filter(appartenance=self.mb).exists())

    def test_secours_apres_desactivation_technique(self):
        Utilisateur.objects.filter(pk=self.a.pk).update(is_active=False)
        operateur = Utilisateur.objects.create_user("operateur", is_staff=True)
        call_command("attribuer_direction_secours", ecole=self.ecole.pk,
            utilisateur=self.b.username, operateur=operateur.username, motif="Récupération fictive", stdout=StringIO())
        self.assertTrue(autorise(self.b, ADMINISTRER_ECOLE, self.ecole))

    def test_promotion_ne_conserve_pas_un_delai_de_grace_precedent(self):
        from comptes.tests_totp import cle_de_test
        DoubleFacteurCompte.objects.create(utilisateur=self.b,
            echeance_le=timezone.now() + timedelta(days=7))
        with override_settings(DOUBLE_FACTEUR_DISPONIBLE=True, DOUBLE_FACTEUR_CLES=[cle_de_test()],
            DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG=1, DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG=6):
            self.accorder()
            self.assertLessEqual(DoubleFacteurCompte.objects.get(utilisateur=self.b).echeance_le, timezone.now())

    def test_promotion_applique_2fa_et_ferme_ancienne_session(self):
        from comptes.tests_totp import cle_de_test
        from suivi.acces_double_facteur import SESSION_EXIGENCE
        client_b = Client()
        client_b.force_login(self.b)
        session = client_b.session
        session[SESSION_EXIGENCE] = ["optionnelle", 9999999999]
        session.save()
        with override_settings(DOUBLE_FACTEUR_DISPONIBLE=True, DOUBLE_FACTEUR_CLES=[cle_de_test()],
            DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG=1, DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG=6):
            self.accorder()
            self.assertLessEqual(DoubleFacteurCompte.objects.get(utilisateur=self.b).echeance_le, timezone.now())
            self.assertNotIn("_auth_user_id", client_b.session)


# SQLite ne fournit pas les verrous de ligne utilisés en production.
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from unittest import skipUnless


@skipUnless(connection.vendor == "postgresql", "Verrous de ligne : PostgreSQL requis")
class RetraitsConcurrents(TransactionTestCase):
    def test_deux_retraits_simultanes_conservent_une_direction(self):
        ecole = Ecole.objects.create(nom="École fictive concurrente")
        responsabilites = []
        for nom in ("premiere", "seconde"):
            u = Utilisateur.objects.create_user(nom)
            m = AppartenanceEcole.objects.create(utilisateur=u, ecole=ecole)
            responsabilites.append(ResponsabiliteEcole.objects.create(appartenance=m))
        depart = Barrier(2)

        def retirer(pk):
            close_old_connections()
            try:
                r = ResponsabiliteEcole.objects.select_related("appartenance__utilisateur").get(pk=pk)
                depart.wait(timeout=10)
                try:
                    terminer_direction(utilisateur=r.appartenance.utilisateur, responsabilite=r)
                    return True
                except ValidationError:
                    return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultats = list(pool.map(retirer, [r.pk for r in responsabilites]))
        self.assertEqual(sorted(resultats), [False, True])
        self.assertEqual(ResponsabiliteEcole.objects.filter(etat="active").count(), 1)
