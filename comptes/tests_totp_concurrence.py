"""Consommations simultanées et reset avec connexions distinctes, sans migration."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections, connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from . import totp
from .models import DoubleFacteurCompte
from .tests_totp import DEPENDANCES, cle_de_test, code_a


@skipUnless(DEPENDANCES, 'requirements-2fa.txt non installé')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConsommationConcurrente(TransactionTestCase):
    def setUp(self):
        reglage = override_settings(DOUBLE_FACTEUR_CLES=[cle_de_test()])
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.user = get_user_model().objects.create_user('concurrent-fictif', password='mot-fictif')
        ligne = totp.commencer_inscription(self.user)
        self.cle = totp.cle_en_cours(ligne)
        self.instant = 1800000000
        self.assertTrue(totp.confirmer_inscription(self.user,
            code_a(self.cle, self.instant - 300), instant=self.instant - 300))
        self.codes = totp.generer_codes_secours(self.user)

    def executer(self, fonction):
        close_old_connections()
        try:
            return fonction()
        finally:
            connections.close_all()

    def test_deux_calculs_du_meme_pas_une_seule_consommation(self):
        barriere = Barrier(2)
        calcul = totp.moteur.verifier_pas
        def calculer(*args, **kwargs):
            pas = calcul(*args, **kwargs)
            barriere.wait(10)
            return pas
        with patch.object(totp.moteur, 'verifier_pas', side_effect=calculer):
            with ThreadPoolExecutor(max_workers=2) as pool:
                resultats = list(pool.map(lambda _: self.executer(lambda: totp.verifier_code(
                    self.user, code_a(self.cle, self.instant), instant=self.instant)), range(2)))
        self.assertEqual(sum(resultats), 1)
        self.assertFalse(totp.verifier_code(self.user, code_a(self.cle, self.instant), instant=self.instant))

    def test_deux_secours_une_seule_consommation(self):
        barriere = Barrier(2)
        def consommer():
            barriere.wait(10)
            return totp.utiliser_code_secours(self.user, self.codes[0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultats = list(pool.map(lambda _: self.executer(consommer), range(2)))
        self.assertEqual(sum(resultats), 1)
        self.assertFalse(totp.utiliser_code_secours(self.user, self.codes[0]))

    def test_reset_commis_apres_calcul_invalide_le_pas(self):
        calcul = totp.moteur.verifier_pas
        def calculer(*args, **kwargs):
            pas = calcul(*args, **kwargs)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.executer, lambda: totp.reinitialiser(self.user)).result(10)
            return pas
        with patch.object(totp.moteur, 'verifier_pas', side_effect=calculer):
            self.assertFalse(totp.verifier_code(self.user,
                code_a(self.cle, self.instant), instant=self.instant))
        ligne = DoubleFacteurCompte.objects.get(utilisateur=self.user)
        self.assertEqual((ligne.dernier_pas, ligne.cle_chiffree), (0, ''))

    def test_stockage_occupe_ne_valide_aucun_facteur(self):
        with patch.object(DoubleFacteurCompte.objects, 'filter', side_effect=DatabaseError('occupé')):
            self.assertFalse(totp.verifier_code(self.user, '123456'))
            self.assertFalse(totp.confirmer_inscription(self.user, '123456'))
            self.assertFalse(totp.utiliser_code_secours(self.user, self.codes[0]))

    def test_verrou_sqlite_reel_refuse_proprement(self):
        if connection.vendor != 'sqlite':
            self.skipTest('Verrouillage spécifique SQLite ; les autres courses restent testées.')
        def verifier():
            connections['default'].ensure_connection()
            connections['default'].connection.execute('PRAGMA busy_timeout=50')
            return totp.verifier_code(self.user, code_a(self.cle, self.instant), instant=self.instant)
        with transaction.atomic():
            DoubleFacteurCompte.objects.filter(utilisateur=self.user).update(dernier_pas=1)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertFalse(pool.submit(self.executer, verifier).result(10))

    def test_reset_commis_pendant_confirmation_ne_reinscrit_pas(self):
        totp.reinitialiser(self.user)
        self.cle = totp.cle_en_cours(totp.commencer_inscription(self.user))
        calcul = totp.moteur.verifier_pas
        def calculer(*args, **kwargs):
            pas = calcul(*args, **kwargs)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(self.executer, lambda: totp.reinitialiser(self.user)).result(10)
            return pas
        with patch.object(totp.moteur, 'verifier_pas', side_effect=calculer):
            self.assertFalse(totp.confirmer_inscription(self.user,
                code_a(self.cle, self.instant), instant=self.instant))
        self.assertFalse(totp.est_inscrit(self.user))
