"""Clé chiffrée, vérification TOTP sans rejeu, QR (#C8c)."""
import time
from importlib.util import find_spec
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from . import totp
from .models import CodeSecoursDoubleFacteur, DoubleFacteurCompte

DEPENDANCES = all(find_spec(n) is not None for n in ("cryptography", "qrcode", "django_otp"))


def cle_de_test():
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def code_a(cle, instant, decalage=0):
    from django_otp.oath import TOTP

    generateur = TOTP(cle, step=totp.PAS, digits=totp.CHIFFRES)
    generateur.time = instant + decalage * totp.PAS
    return f"{generateur.token():06d}"


@skipUnless(DEPENDANCES, "requirements-2fa.txt non installé")
class Totp(TestCase):
    def setUp(self):
        self.cle_chiffrement = cle_de_test()
        reglage = override_settings(DOUBLE_FACTEUR_CLES=[self.cle_chiffrement])
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.utilisateur = get_user_model().objects.create_user("ines", password="x" * 14)
        self.instant = 1_800_000_000

    def _inscrit(self):
        compte = totp.commencer_inscription(self.utilisateur)
        cle = totp.cle_en_cours(compte)
        self.assertTrue(totp.confirmer_inscription(
            self.utilisateur, code_a(cle, self.instant), instant=self.instant))
        return cle

    def test_vecteur_rfc_6238(self):
        from django_otp.oath import TOTP

        generateur = TOTP(b"12345678901234567890", step=30, digits=8)
        generateur.time = 59
        self.assertEqual(generateur.token(), 94287082)

    def test_la_cle_n_est_jamais_en_clair_en_base(self):
        compte = totp.commencer_inscription(self.utilisateur)
        cle = totp.cle_en_cours(compte)
        brut = DoubleFacteurCompte.objects.get(pk=compte.pk).cle_chiffree
        self.assertNotIn(totp.cle_en_base32(cle), brut)
        self.assertNotIn(cle.hex(), brut)
        self.assertEqual(totp.dechiffrer(brut), cle)

    def test_la_cle_est_reprise_tant_que_l_inscription_n_est_pas_confirmee(self):
        premiere = totp.cle_en_cours(totp.commencer_inscription(self.utilisateur))
        seconde = totp.cle_en_cours(totp.commencer_inscription(self.utilisateur))
        self.assertEqual(premiere, seconde)
        self.assertFalse(totp.est_inscrit(self.utilisateur))

    def test_inscription_confirmee_par_un_premier_code_valide(self):
        self._inscrit()
        self.assertTrue(totp.est_inscrit(self.utilisateur))
        compte = DoubleFacteurCompte.objects.get(utilisateur=self.utilisateur)
        self.assertIsNotNone(compte.confirme_le)
        self.assertIsNone(compte.echeance_le)

    def test_un_code_faux_ne_confirme_rien(self):
        compte = totp.commencer_inscription(self.utilisateur)
        cle = totp.cle_en_cours(compte)
        faux = f"{(int(code_a(cle, self.instant)) + 1) % 1_000_000:06d}"
        self.assertFalse(totp.confirmer_inscription(self.utilisateur, faux, instant=self.instant))
        self.assertFalse(totp.est_inscrit(self.utilisateur))

    def test_la_cle_d_un_compte_inscrit_ne_s_affiche_plus(self):
        self._inscrit()
        compte = DoubleFacteurCompte.objects.get(utilisateur=self.utilisateur)
        with self.assertRaises(ValidationError):
            totp.cle_en_cours(compte)
        with self.assertRaises(ValidationError):
            totp.commencer_inscription(self.utilisateur)

    def test_tolerance_d_un_pas_de_chaque_cote(self):
        cle = self._inscrit()
        apres = self.instant + 3 * totp.PAS
        self.assertTrue(totp.verifier_code(self.utilisateur, code_a(cle, apres, -1), instant=apres))
        suivant = apres + 3 * totp.PAS
        self.assertTrue(totp.verifier_code(self.utilisateur, code_a(cle, suivant, +1), instant=suivant))

    def test_deux_pas_d_ecart_sont_refuses(self):
        cle = self._inscrit()
        apres = self.instant + 10 * totp.PAS
        self.assertFalse(totp.verifier_code(self.utilisateur, code_a(cle, apres, -2), instant=apres))
        self.assertFalse(totp.verifier_code(self.utilisateur, code_a(cle, apres, +2), instant=apres))

    def test_un_code_ne_peut_pas_etre_rejoue(self):
        cle = self._inscrit()
        instant = self.instant + 5 * totp.PAS
        code = code_a(cle, instant)
        self.assertTrue(totp.verifier_code(self.utilisateur, code, instant=instant))
        self.assertFalse(totp.verifier_code(self.utilisateur, code, instant=instant))
        self.assertFalse(totp.verifier_code(self.utilisateur, code, instant=instant + 5))

    def test_le_code_de_confirmation_ne_se_rejoue_pas_a_la_connexion(self):
        cle = self._inscrit()
        self.assertFalse(totp.verifier_code(
            self.utilisateur, code_a(cle, self.instant), instant=self.instant))

    def test_un_code_plus_ancien_que_le_dernier_accepte_est_refuse(self):
        cle = self._inscrit()
        recent = self.instant + 8 * totp.PAS
        self.assertTrue(totp.verifier_code(self.utilisateur, code_a(cle, recent), instant=recent))
        ancien = self.instant + 6 * totp.PAS
        self.assertFalse(totp.verifier_code(self.utilisateur, code_a(cle, ancien), instant=recent))

    def test_formats_de_code_invalides(self):
        cle = self._inscrit()
        instant = self.instant + 4 * totp.PAS
        bon = code_a(cle, instant)
        for code in ("", "12345", "1234567", "abcdef", "١٢٣٤٥٦", None, "12 34 5"):
            with self.subTest(code):
                self.assertFalse(totp.verifier_code(self.utilisateur, code, instant=instant))
        spacieux = f"{bon[:3]} {bon[3:]}"
        self.assertTrue(totp.verifier_code(self.utilisateur, spacieux, instant=instant))

    def test_compte_sans_inscription_refuse_tout_code(self):
        self.assertFalse(totp.verifier_code(self.utilisateur, "123456", instant=self.instant))

    def test_rotation_de_la_cle_de_chiffrement(self):
        cle = self._inscrit()
        nouvelle = cle_de_test()
        with override_settings(DOUBLE_FACTEUR_CLES=[nouvelle, self.cle_chiffrement]):
            instant = self.instant + 4 * totp.PAS
            self.assertTrue(totp.verifier_code(self.utilisateur, code_a(cle, instant), instant=instant))
        with override_settings(DOUBLE_FACTEUR_CLES=[nouvelle]):
            instant = self.instant + 9 * totp.PAS
            with self.assertLogs("comptes.totp", level="ERROR"):
                self.assertFalse(totp.verifier_code(self.utilisateur, code_a(cle, instant), instant=instant))

    def test_uri_et_qr(self):
        compte = totp.commencer_inscription(self.utilisateur)
        cle = totp.cle_en_cours(compte)
        uri = totp.uri_otpauth(self.utilisateur, cle)
        self.assertTrue(uri.startswith("otpauth://totp/Petits%20Pas%3Aines?secret="))
        self.assertIn(totp.cle_en_base32(cle), uri)
        self.assertIn("issuer=Petits%20Pas", uri)
        svg = totp.qr_svg(uri)
        self.assertTrue(svg.startswith("<svg"))
        self.assertNotIn("<?xml", svg)

    def test_retirer_supprime_l_etat(self):
        self._inscrit()
        totp.retirer(self.utilisateur)
        self.assertFalse(totp.est_inscrit(self.utilisateur))
        self.assertFalse(DoubleFacteurCompte.objects.exists())

    # --- Codes de secours -------------------------------------------------

    def test_dix_codes_distincts_au_bon_format(self):
        self._inscrit()
        codes = totp.generer_codes_secours(self.utilisateur)
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        for code in codes:
            self.assertRegex(code, r"^[A-HJ-NP-Z2-9]{4}(-[A-HJ-NP-Z2-9]{4}){3}$")
        self.assertEqual(totp.codes_secours_restants(self.utilisateur), 10)

    def test_seules_les_empreintes_sont_conservees(self):
        self._inscrit()
        codes = totp.generer_codes_secours(self.utilisateur)
        stocke = " ".join(CodeSecoursDoubleFacteur.objects.values_list("empreinte", flat=True))
        for code in codes:
            self.assertNotIn(code.replace("-", ""), stocke)
            self.assertNotIn(code, stocke)
        self.assertTrue(all(len(e) == 64 for e in CodeSecoursDoubleFacteur.objects.values_list("empreinte", flat=True)))

    def test_un_code_de_secours_ne_sert_qu_une_fois(self):
        self._inscrit()
        code = totp.generer_codes_secours(self.utilisateur)[0]
        self.assertTrue(totp.utiliser_code_secours(self.utilisateur, code))
        self.assertFalse(totp.utiliser_code_secours(self.utilisateur, code))
        self.assertEqual(totp.codes_secours_restants(self.utilisateur), 9)

    def test_la_saisie_est_tolerante_sur_la_casse_les_espaces_et_les_tirets(self):
        self._inscrit()
        codes = totp.generer_codes_secours(self.utilisateur)
        brut = codes[0].replace("-", "").lower()
        self.assertTrue(totp.utiliser_code_secours(self.utilisateur, f" {brut[:8]} {brut[8:]} "))
        self.assertTrue(totp.utiliser_code_secours(self.utilisateur, codes[1].replace("-", " ")))

    def test_codes_invalides_refuses(self):
        self._inscrit()
        code = totp.generer_codes_secours(self.utilisateur)[0]
        for saisie in ("", None, "123456", code[:-1], code + "A", "I" * 16, "0" * 16, "AAAA-AAAA-AAAA-AAAA"):
            with self.subTest(saisie):
                self.assertFalse(totp.utiliser_code_secours(self.utilisateur, saisie))
        self.assertEqual(totp.codes_secours_restants(self.utilisateur), 10)

    def test_les_codes_d_un_compte_ne_servent_pas_a_un_autre(self):
        self._inscrit()
        code = totp.generer_codes_secours(self.utilisateur)[0]
        autre = get_user_model().objects.create_user("autre", password="x" * 14)
        compte = totp.commencer_inscription(autre)
        DoubleFacteurCompte.objects.filter(pk=compte.pk).update(confirme_le=compte.cree_le)
        self.assertFalse(totp.utiliser_code_secours(autre, code))
        self.assertTrue(totp.utiliser_code_secours(self.utilisateur, code))

    def test_regenerer_invalide_les_anciens_codes(self):
        self._inscrit()
        anciens = totp.generer_codes_secours(self.utilisateur)
        nouveaux = totp.generer_codes_secours(self.utilisateur)
        self.assertFalse(set(anciens) & set(nouveaux))
        self.assertFalse(totp.utiliser_code_secours(self.utilisateur, anciens[0]))
        self.assertTrue(totp.utiliser_code_secours(self.utilisateur, nouveaux[0]))
        self.assertEqual(CodeSecoursDoubleFacteur.objects.filter(utilisateur=self.utilisateur).count(), 10)

    def test_pas_de_codes_sans_second_facteur_confirme(self):
        with self.assertRaises(ValidationError):
            totp.generer_codes_secours(self.utilisateur)
        totp.commencer_inscription(self.utilisateur)
        with self.assertRaises(ValidationError):
            totp.generer_codes_secours(self.utilisateur)

    def test_un_code_n_est_pas_utilisable_sans_inscription(self):
        self._inscrit()
        code = totp.generer_codes_secours(self.utilisateur)[0]
        DoubleFacteurCompte.objects.filter(utilisateur=self.utilisateur).update(confirme_le=None)
        self.assertFalse(totp.utiliser_code_secours(self.utilisateur, code))

    def test_retirer_supprime_aussi_les_codes(self):
        self._inscrit()
        totp.generer_codes_secours(self.utilisateur)
        totp.retirer(self.utilisateur)
        self.assertFalse(CodeSecoursDoubleFacteur.objects.exists())

    def test_reinitialiser_efface_cle_et_codes_mais_garde_la_ligne(self):
        self._inscrit()
        totp.generer_codes_secours(self.utilisateur)
        DoubleFacteurCompte.objects.filter(utilisateur=self.utilisateur).update(dernier_pas=99)
        totp.reinitialiser(self.utilisateur)
        compte = DoubleFacteurCompte.objects.get(utilisateur=self.utilisateur)
        self.assertEqual((compte.cle_chiffree, compte.confirme_le, compte.dernier_pas), ("", None, 0))
        self.assertFalse(totp.est_inscrit(self.utilisateur))
        self.assertFalse(CodeSecoursDoubleFacteur.objects.exists())
        # Une nouvelle inscription repart d'une clé neuve.
        self.assertTrue(totp.cle_en_cours(totp.commencer_inscription(self.utilisateur)))
