"""Politique de 2FA hiérarchique : variables du déployeur, politique de l'école,
rangs de fonction et exigence effective d'un compte (#C8b). Aucun TOTP ici."""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from carnet.double_facteur import (
    ASSOCIE, CONTRIBUTEUR, DIRECTION, RESPONSABLE, SANS_FONCTION,
    politique_deployeur_depuis_environnement as lire,
)
from comptes.models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole

from .double_facteur import (
    Exigence, PolitiqueEffective, combiner, exigence_double_facteur, politique_ecole,
    rang_le_plus_haut, rangs_par_ecole,
)
from .models import Classe, Ecole, EvenementAudit, PolitiqueDoubleFacteurEcole
from .services.double_facteur import enregistrer_politique_ecole, lire_politique_ecole

OBLIGATOIRE_DEPLOYEUR = "DOUBLE_FACTEUR_OBLIGATOIRE_JUSQU_AU_RANG"
DESACTIVE_DEPLOYEUR = "DOUBLE_FACTEUR_DESACTIVE_A_PARTIR_DU_RANG"


class VariablesDuDeployeur(SimpleTestCase):
    def test_absentes_le_2fa_reste_optionnel_pour_tous(self):
        self.assertEqual(lire({}), (0, 6))

    def test_noms_de_rangs(self):
        env = {"CARNET_2FA_OBLIGATOIRE": "Direction", "CARNET_2FA_DESACTIVE_POUR": " contributeur "}
        self.assertEqual(lire(env), (DIRECTION, CONTRIBUTEUR))

    def test_tous_vaut_personne_sans_fonction(self):
        self.assertEqual(lire({"CARNET_2FA_OBLIGATOIRE": "tous"}), (SANS_FONCTION, 6))
        self.assertEqual(lire({"CARNET_2FA_DESACTIVE_POUR": "tous"}), (0, SANS_FONCTION))

    def test_valeurs_neutres_explicites(self):
        env = {"CARNET_2FA_OBLIGATOIRE": "aucun", "CARNET_2FA_DESACTIVE_POUR": "jamais"}
        self.assertEqual(lire(env), (0, 6))

    def test_faute_de_frappe_refusee_au_lieu_d_etre_ignoree(self):
        with self.assertRaises(ImproperlyConfigured):
            lire({"CARNET_2FA_OBLIGATOIRE": "direciton"})
        with self.assertRaises(ImproperlyConfigured):
            lire({"CARNET_2FA_DESACTIVE_POUR": "3"})

    def test_obligatoire_et_desactive_pour_une_meme_fonction_refuse(self):
        env = {"CARNET_2FA_OBLIGATOIRE": "contributeur", "CARNET_2FA_DESACTIVE_POUR": "associe"}
        with self.assertRaises(ImproperlyConfigured):
            lire(env)
        env["CARNET_2FA_DESACTIVE_POUR"] = "contributeur"
        with self.assertRaises(ImproperlyConfigured):
            lire(env)

    def test_mode_local_desactive_des_la_direction(self):
        env = {"CARNET_2FA_OBLIGATOIRE": "direction"}
        self.assertEqual(lire(env, mode_local=True), (0, DIRECTION))


class Combinaison(SimpleTestCase):
    def test_sans_politique_d_ecole_celle_du_deployeur(self):
        effective = combiner(PolitiqueEffective(1, 5))
        self.assertEqual((effective.obligatoire_jusqu_au_rang, effective.desactive_a_partir_du_rang), (1, 5))
        self.assertEqual(effective.avertissements, ())

    def test_l_ecole_peut_durcir_et_desactiver_sous_le_deployeur(self):
        effective = combiner(PolitiqueEffective(1, 6), obligatoire_ecole=3, desactive_ecole=5)
        self.assertEqual((effective.obligatoire_jusqu_au_rang, effective.desactive_a_partir_du_rang), (3, 5))

    def test_une_obligation_recue_ne_se_baisse_pas(self):
        effective = combiner(PolitiqueEffective(3, 6), obligatoire_ecole=1)
        self.assertEqual(effective.obligatoire_jusqu_au_rang, 3)

    def test_ce_qui_est_desactive_au_dessus_ne_se_rouvre_pas(self):
        effective = combiner(PolitiqueEffective(0, 4), desactive_ecole=6)
        self.assertEqual(effective.desactive_a_partir_du_rang, 4)

    def test_desactivation_de_l_ecole_devenue_incompatible_est_ecartee(self):
        # L'école avait désactivé dès le rang 3 ; le déployeur rend ensuite le rang 3 obligatoire.
        # Le rang 3 reste obligatoire ; la désactivation voulue vaut pour les rangs suivants.
        effective = combiner(PolitiqueEffective(3, 6), desactive_ecole=3)
        self.assertEqual((effective.obligatoire_jusqu_au_rang, effective.desactive_a_partir_du_rang), (3, 4))
        self.assertTrue(effective.avertissements)

    def test_obligation_de_l_ecole_devenue_incompatible_est_limitee(self):
        # L'école exigeait jusqu'au rang 4 ; le déployeur désactive ensuite dès le rang 4.
        effective = combiner(PolitiqueEffective(0, 4), obligatoire_ecole=4)
        self.assertEqual((effective.obligatoire_jusqu_au_rang, effective.desactive_a_partir_du_rang), (3, 4))
        self.assertTrue(effective.avertissements)

    def test_exigence_par_rang(self):
        politique = PolitiqueEffective(2, 4)
        self.assertEqual(politique.exigence_pour_rang(DIRECTION), Exigence.OBLIGATOIRE)
        self.assertEqual(politique.exigence_pour_rang(RESPONSABLE), Exigence.OBLIGATOIRE)
        self.assertEqual(politique.exigence_pour_rang(ASSOCIE), Exigence.OPTIONNELLE)
        self.assertEqual(politique.exigence_pour_rang(CONTRIBUTEUR), Exigence.DESACTIVEE)
        self.assertEqual(politique.exigence_pour_rang(SANS_FONCTION), Exigence.DESACTIVEE)


class BaseEcoles(TestCase):
    def setUp(self):
        self.aujourdhui = timezone.localdate()
        self.ecole_a = Ecole.objects.create(nom="École A")
        self.ecole_b = Ecole.objects.create(nom="École B")
        self.classe_a = Classe.objects.create(ecole=self.ecole_a, nom="A1")
        self.classe_b = Classe.objects.create(ecole=self.ecole_b, nom="B1")
        self.direction, self.direction_a = self._membre("direction", self.ecole_a)
        ResponsabiliteEcole.objects.create(appartenance=self.direction_a)
        self.responsable, self.responsable_a = self._membre("responsable", self.ecole_a)
        self.associe, self.associe_a = self._membre("associe", self.ecole_a)
        self.contributeur, self.contributeur_a = self._membre("contributeur", self.ecole_a)
        self.sans_fonction, _ = self._membre("sans-fonction", self.ecole_a)
        self.direction_b, self.direction_bb = self._membre("direction-b", self.ecole_b)
        ResponsabiliteEcole.objects.create(appartenance=self.direction_bb)
        self.responsable_b, self.responsable_bb = self._membre("responsable-b", self.ecole_b)
        self._affecter(self.responsable_a, self.classe_a, AffectationClasse.RESPONSABLE)
        self._affecter(self.associe_a, self.classe_a, AffectationClasse.ENSEIGNANT_ASSOCIE)
        self._affecter(self.contributeur_a, self.classe_a, AffectationClasse.CONTRIBUTEUR)
        self._affecter(self.responsable_bb, self.classe_b, AffectationClasse.RESPONSABLE)
        self.classe_a.activer()
        self.classe_b.activer()

    def _membre(self, nom, ecole):
        utilisateur = get_user_model().objects.create_user(nom)
        return utilisateur, AppartenanceEcole.objects.create(utilisateur=utilisateur, ecole=ecole)

    def _affecter(self, appartenance, classe, type, **champs):
        return AffectationClasse.objects.create(
            appartenance=appartenance, classe=classe, type=type, **champs)

    def _politique_ecole(self, ecole, obligatoire=0, desactive=6):
        return PolitiqueDoubleFacteurEcole.objects.update_or_create(
            ecole=ecole,
            defaults={"obligatoire_jusqu_au_rang": obligatoire, "desactive_a_partir_du_rang": desactive})[0]


class Rangs(BaseEcoles):
    def test_rang_par_fonction(self):
        attendus = {
            self.direction: DIRECTION, self.responsable: RESPONSABLE, self.associe: ASSOCIE,
            self.contributeur: CONTRIBUTEUR, self.sans_fonction: SANS_FONCTION,
        }
        for utilisateur, rang in attendus.items():
            with self.subTest(utilisateur.username):
                self.assertEqual(rangs_par_ecole(utilisateur), {self.ecole_a.pk: rang})

    def test_le_rang_le_plus_haut_l_emporte_dans_une_ecole(self):
        self._affecter(self.contributeur_a, Classe.objects.create(ecole=self.ecole_a, nom="A2"),
                       AffectationClasse.CONTRIBUTEUR)
        ResponsabiliteEcole.objects.create(appartenance=self.associe_a)
        self.assertEqual(rangs_par_ecole(self.associe), {self.ecole_a.pk: DIRECTION})

    def test_rang_par_ecole_pour_un_compte_multi_ecoles(self):
        multi, multi_a = self._membre("multi", self.ecole_a)
        multi_b = AppartenanceEcole.objects.create(utilisateur=multi, ecole=self.ecole_b)
        self._affecter(multi_a, self.classe_a, AffectationClasse.ENSEIGNANT_ASSOCIE)
        self._affecter(multi_b, self.classe_b, AffectationClasse.CONTRIBUTEUR)
        self.assertEqual(rangs_par_ecole(multi), {self.ecole_a.pk: ASSOCIE, self.ecole_b.pk: CONTRIBUTEUR})
        self.assertEqual(rang_le_plus_haut(multi), ASSOCIE)

    def test_une_affectation_terminee_ou_future_ne_compte_pas(self):
        passe, passe_a = self._membre("passe", self.ecole_a)
        self._affecter(passe_a, self.classe_a, AffectationClasse.RESPONSABLE,
                       date_debut=self.aujourdhui - datetime.timedelta(days=9),
                       date_fin=self.aujourdhui - datetime.timedelta(days=2))
        futur, futur_a = self._membre("futur", self.ecole_a)
        self._affecter(futur_a, self.classe_a, AffectationClasse.RESPONSABLE,
                       date_debut=self.aujourdhui + datetime.timedelta(days=3))
        self.assertEqual(rangs_par_ecole(passe), {self.ecole_a.pk: SANS_FONCTION})
        self.assertEqual(rangs_par_ecole(futur), {self.ecole_a.pk: SANS_FONCTION})
        self.assertEqual(rangs_par_ecole(futur, self.aujourdhui + datetime.timedelta(days=3)),
                         {self.ecole_a.pk: RESPONSABLE})

    def test_une_classe_en_preparation_ne_donne_pas_encore_de_rang(self):
        prepa = Classe.objects.create(ecole=self.ecole_a, nom="En préparation")
        nouveau, nouveau_a = self._membre("nouveau", self.ecole_a)
        self._affecter(nouveau_a, prepa, AffectationClasse.RESPONSABLE)
        self.assertEqual(rangs_par_ecole(nouveau), {self.ecole_a.pk: SANS_FONCTION})

    def test_appartenance_terminee_ou_ecole_inactive_sans_rang(self):
        self.contributeur_a.etat = AppartenanceEcole.TERMINEE
        self.contributeur_a.save()
        self.assertEqual(rangs_par_ecole(self.contributeur), {})
        self.ecole_b.etat = Ecole.DESACTIVEE
        self.ecole_b.save()
        self.assertEqual(rangs_par_ecole(self.direction_b), {})


class ExigenceEffective(BaseEcoles):
    def exigence(self, utilisateur):
        return exigence_double_facteur(utilisateur)

    def test_sans_politique_tout_le_monde_est_optionnel(self):
        for utilisateur in (self.direction, self.responsable, self.contributeur, self.sans_fonction):
            self.assertEqual(self.exigence(utilisateur), Exigence.OPTIONNELLE)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: DIRECTION})
    def test_le_deployeur_rend_la_direction_obligatoire_partout(self):
        self.assertEqual(self.exigence(self.direction), Exigence.OBLIGATOIRE)
        self.assertEqual(self.exigence(self.direction_b), Exigence.OBLIGATOIRE)
        self.assertEqual(self.exigence(self.responsable), Exigence.OPTIONNELLE)

    def test_l_ecole_durcit_sans_toucher_aux_autres_ecoles(self):
        self._politique_ecole(self.ecole_a, obligatoire=ASSOCIE)
        self.assertEqual(self.exigence(self.associe), Exigence.OBLIGATOIRE)
        self.assertEqual(self.exigence(self.contributeur), Exigence.OPTIONNELLE)
        self.assertEqual(self.exigence(self.responsable_b), Exigence.OPTIONNELLE)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_l_ecole_ne_baisse_pas_l_obligation_du_deployeur(self):
        self._politique_ecole(self.ecole_a, obligatoire=0, desactive=ASSOCIE)
        self.assertEqual(self.exigence(self.associe), Exigence.OBLIGATOIRE)

    def test_l_ecole_peut_desactiver_la_ou_rien_n_est_obligatoire(self):
        self._politique_ecole(self.ecole_a, desactive=CONTRIBUTEUR)
        self.assertEqual(self.exigence(self.associe), Exigence.OPTIONNELLE)
        self.assertEqual(self.exigence(self.contributeur), Exigence.DESACTIVEE)
        self.assertEqual(self.exigence(self.sans_fonction), Exigence.DESACTIVEE)

    @override_settings(**{DESACTIVE_DEPLOYEUR: CONTRIBUTEUR})
    def test_ce_que_le_deployeur_desactive_ne_se_rouvre_pas(self):
        self._politique_ecole(self.ecole_a, obligatoire=CONTRIBUTEUR - 1)
        self.assertEqual(self.exigence(self.contributeur), Exigence.DESACTIVEE)
        self.assertEqual(self.exigence(self.associe), Exigence.OBLIGATOIRE)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: 0, DESACTIVE_DEPLOYEUR: DIRECTION})
    def test_mode_local_tout_est_desactive(self):
        for utilisateur in (self.direction, self.responsable, self.sans_fonction):
            self.assertEqual(self.exigence(utilisateur), Exigence.DESACTIVEE)

    def _multi(self):
        multi, multi_a = self._membre("multi", self.ecole_a)
        multi_b = AppartenanceEcole.objects.create(utilisateur=multi, ecole=self.ecole_b)
        self._affecter(multi_a, self.classe_a, AffectationClasse.ENSEIGNANT_ASSOCIE)
        self._affecter(multi_b, self.classe_b, AffectationClasse.CONTRIBUTEUR)
        return multi

    def test_multi_ecoles_une_seule_obligation_suffit(self):
        multi = self._multi()
        self._politique_ecole(self.ecole_a, obligatoire=ASSOCIE)
        self._politique_ecole(self.ecole_b, desactive=CONTRIBUTEUR)
        self.assertEqual(self.exigence(multi), Exigence.OBLIGATOIRE)

    def test_multi_ecoles_une_ecole_qui_desactive_ne_suffit_pas(self):
        multi = self._multi()
        self._politique_ecole(self.ecole_a, desactive=ASSOCIE)
        self.assertEqual(self.exigence(multi), Exigence.OPTIONNELLE)

    def test_multi_ecoles_desactive_si_toutes_desactivent(self):
        multi = self._multi()
        self._politique_ecole(self.ecole_a, desactive=ASSOCIE)
        self._politique_ecole(self.ecole_b, desactive=CONTRIBUTEUR)
        self.assertEqual(self.exigence(multi), Exigence.DESACTIVEE)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: SANS_FONCTION})
    def test_sans_appartenance_seul_le_deployeur_s_applique(self):
        isole = get_user_model().objects.create_user("isole")
        self.assertEqual(self.exigence(isole), Exigence.OBLIGATOIRE)

    def test_sans_appartenance_sans_politique_c_est_optionnel(self):
        isole = get_user_model().objects.create_user("isole")
        self.assertEqual(self.exigence(isole), Exigence.OPTIONNELLE)

    def test_compte_inactif_ou_anonyme_n_est_pas_soumis(self):
        self.direction.is_active = False
        self.direction.save()
        self.assertEqual(self.exigence(self.direction), Exigence.DESACTIVEE)
        self.assertEqual(self.exigence(AnonymousUser()), Exigence.DESACTIVEE)

    def test_l_exigence_suit_les_fonctions_actuelles(self):
        self._politique_ecole(self.ecole_a, obligatoire=RESPONSABLE)
        self.assertEqual(self.exigence(self.associe), Exigence.OPTIONNELLE)
        seconde = Classe.objects.create(ecole=self.ecole_a, nom="A2")
        self._affecter(self.associe_a, seconde, AffectationClasse.RESPONSABLE)
        seconde.activer()
        self.assertEqual(self.exigence(self.associe), Exigence.OBLIGATOIRE)

    @override_settings(**{DESACTIVE_DEPLOYEUR: CONTRIBUTEUR})
    def test_politique_d_ecole_devenue_incompatible_signale_sans_rien_modifier(self):
        stockee = self._politique_ecole(self.ecole_a, obligatoire=CONTRIBUTEUR)
        effective = politique_ecole(self.ecole_a)
        self.assertEqual(effective.obligatoire_jusqu_au_rang, ASSOCIE)
        self.assertTrue(effective.avertissements)
        stockee.refresh_from_db()
        self.assertEqual(stockee.obligatoire_jusqu_au_rang, CONTRIBUTEUR)


class ContraintesDuModele(BaseEcoles):
    def test_obligatoire_et_desactive_incoherents_refuses_en_base(self):
        for obligatoire, desactive in [(3, 3), (4, 2), (6, 6), (0, 0)]:
            with self.subTest((obligatoire, desactive)), self.assertRaises(IntegrityError), transaction.atomic():
                PolitiqueDoubleFacteurEcole.objects.create(
                    ecole=self.ecole_a, obligatoire_jusqu_au_rang=obligatoire,
                    desactive_a_partir_du_rang=desactive)

    def test_valeurs_par_defaut_n_ajoutent_rien(self):
        politique = PolitiqueDoubleFacteurEcole.objects.create(ecole=self.ecole_a)
        self.assertEqual((politique.obligatoire_jusqu_au_rang, politique.desactive_a_partir_du_rang), (0, 6))


class ServicePolitiqueEcole(BaseEcoles):
    def enregistrer(self, utilisateur=None, ecole=None, obligatoire=2, desactive=5, revision=0):
        return enregistrer_politique_ecole(
            utilisateur=utilisateur or self.direction, ecole=ecole or self.ecole_a,
            obligatoire_jusqu_au_rang=obligatoire, desactive_a_partir_du_rang=desactive,
            revision_attendue=revision)

    def test_la_direction_enregistre_journalise_et_incremente_la_revision(self):
        politique = self.enregistrer()
        self.assertEqual((politique.obligatoire_jusqu_au_rang, politique.desactive_a_partir_du_rang), (2, 5))
        self.assertEqual(politique.revision, 1)
        evenement = EvenementAudit.objects.get(action="securite.double_facteur_ecole")
        self.assertEqual(evenement.ecole, self.ecole_a)
        self.assertEqual(evenement.acteur, self.direction)
        self.assertEqual(evenement.anciennes_valeurs["obligatoire_jusqu_au_rang"], 0)
        self.assertEqual(evenement.nouvelles_valeurs["obligatoire_jusqu_au_rang"], 2)
        self.assertEqual(self.exigence_responsable(), Exigence.OBLIGATOIRE)

    def exigence_responsable(self):
        return exigence_double_facteur(self.responsable)

    def test_seule_la_direction_de_l_ecole_peut_ecrire_et_lire(self):
        for utilisateur in (self.responsable, self.associe, self.contributeur, self.sans_fonction,
                            self.direction_b):
            with self.subTest(utilisateur.username):
                with self.assertRaises(PermissionDenied):
                    self.enregistrer(utilisateur)
                with self.assertRaises(PermissionDenied):
                    lire_politique_ecole(utilisateur=utilisateur, ecole=self.ecole_a)
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    def test_revision_perimee_refusee(self):
        self.enregistrer()
        with self.assertRaises(ValidationError):
            self.enregistrer(revision=0)
        self.assertEqual(self.enregistrer(obligatoire=3, revision=1).revision, 2)

    def test_revision_invalide_refusee(self):
        for revision in (-1, "0", None, 1.0, True):
            with self.subTest(revision), self.assertRaises(ValidationError):
                self.enregistrer(revision=revision)

    def test_curseurs_incoherents_refuses(self):
        for obligatoire, desactive in [(3, 3), (4, 2), (6, 6), (0, 0), (0, 7), (-1, 6), ("1", 6), (True, 6)]:
            with self.subTest((obligatoire, desactive)), self.assertRaises(ValidationError):
                self.enregistrer(obligatoire=obligatoire, desactive=desactive)
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE})
    def test_refuse_de_desactiver_ce_que_le_deployeur_impose(self):
        with self.assertRaises(ValidationError):
            self.enregistrer(obligatoire=0, desactive=ASSOCIE)
        self.enregistrer(obligatoire=0, desactive=CONTRIBUTEUR)

    @override_settings(**{DESACTIVE_DEPLOYEUR: CONTRIBUTEUR})
    def test_refuse_de_rendre_obligatoire_ce_que_le_deployeur_desactive(self):
        with self.assertRaises(ValidationError):
            self.enregistrer(obligatoire=CONTRIBUTEUR, desactive=6)
        self.enregistrer(obligatoire=ASSOCIE, desactive=6)

    @override_settings(**{OBLIGATOIRE_DEPLOYEUR: ASSOCIE, DESACTIVE_DEPLOYEUR: 5})
    def test_valeurs_moins_strictes_que_le_deployeur_acceptees_sans_effet(self):
        politique = self.enregistrer(obligatoire=1, desactive=6)
        self.assertEqual((politique.obligatoire_jusqu_au_rang, politique.desactive_a_partir_du_rang), (1, 6))
        effective = politique_ecole(self.ecole_a)
        self.assertEqual((effective.obligatoire_jusqu_au_rang, effective.desactive_a_partir_du_rang), (3, 5))

    def test_lecture_pour_la_direction(self):
        self.enregistrer()
        lecture = lire_politique_ecole(utilisateur=self.direction, ecole=self.ecole_a)
        self.assertEqual((lecture["obligatoire_jusqu_au_rang"], lecture["desactive_a_partir_du_rang"],
                          lecture["revision"]), (2, 5, 1))
        self.assertEqual(lecture["effective"].obligatoire_jusqu_au_rang, 2)

    def test_lecture_sans_politique_ne_cree_aucune_ligne(self):
        lecture = lire_politique_ecole(utilisateur=self.direction, ecole=self.ecole_a)
        self.assertEqual((lecture["obligatoire_jusqu_au_rang"], lecture["desactive_a_partir_du_rang"],
                          lecture["revision"]), (0, 6, 0))
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.exists())

    def test_cloisonnement_entre_ecoles(self):
        self.enregistrer()
        self.assertEqual(exigence_double_facteur(self.responsable_b), Exigence.OPTIONNELLE)
        self.assertFalse(PolitiqueDoubleFacteurEcole.objects.filter(ecole=self.ecole_b).exists())
