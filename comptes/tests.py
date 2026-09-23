import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from suivi.models import Classe, Ecole

from .models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole


class ModeleAffectations(TestCase):
    def setUp(self):
        self.utilisateur = get_user_model().objects.create_user("alice")
        self.ecole = Ecole.objects.create(nom="Les Tilleuls")
        self.appartenance = AppartenanceEcole.objects.create(
            utilisateur=self.utilisateur,
            ecole=self.ecole,
        )
        self.classe = Classe.objects.create(ecole=self.ecole, nom="PS-MS")

    def test_utilisateur_multi_ecoles_et_multi_classes(self):
        autre_ecole = Ecole.objects.create(nom="Les Marronniers")
        autre_appartenance = AppartenanceEcole.objects.create(
            utilisateur=self.utilisateur,
            ecole=autre_ecole,
        )
        autre_classe = Classe.objects.create(ecole=autre_ecole, nom="GS")
        seconde_classe = Classe.objects.create(ecole=self.ecole, nom="MS-GS")

        AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.RESPONSABLE,
        )
        AffectationClasse.objects.create(
            appartenance=autre_appartenance,
            classe=autre_classe,
            type=AffectationClasse.ENSEIGNANT_ASSOCIE,
        )
        AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=seconde_classe,
            type=AffectationClasse.CONTRIBUTEUR,
        )

        self.assertEqual(self.utilisateur.appartenances_ecoles.count(), 2)
        self.assertEqual(
            AffectationClasse.objects.filter(
                appartenance__utilisateur=self.utilisateur
            ).count(),
            3,
        )

    def test_deux_appartenances_simultanees_a_la_meme_ecole_refusees(self):
        with self.assertRaises(ValidationError):
            AppartenanceEcole.objects.create(
                utilisateur=self.utilisateur,
                ecole=self.ecole,
            )

    def test_suspension_de_l_appartenance_desactive_l_affectation(self):
        affectation = AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.RESPONSABLE,
        )
        self.classe.activer()
        self.appartenance.etat = AppartenanceEcole.SUSPENDUE
        self.appartenance.save(update_fields=["etat"])

        self.assertFalse(affectation.est_active())

    def test_affectations_future_active_et_expiree(self):
        aujourd_hui = timezone.localdate()
        future = AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.RESPONSABLE,
            date_debut=aujourd_hui + datetime.timedelta(days=1),
        )
        expiree = AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.CONTRIBUTEUR,
            date_debut=aujourd_hui - datetime.timedelta(days=10),
            date_fin=aujourd_hui - datetime.timedelta(days=1),
        )

        self.assertFalse(future.est_active())
        self.assertFalse(expiree.est_active())
        self.assertFalse(
            AffectationClasse.objects.a_la_date(aujourd_hui).filter(pk=future.pk).exists()
        )
        self.assertFalse(
            AffectationClasse.objects.a_la_date(aujourd_hui)
            .filter(pk=expiree.pk)
            .exists()
        )

    def test_acces_historique_rend_active_une_affectation_de_classe_archivee(self):
        self.classe.etat = Classe.ARCHIVEE
        self.classe.save(update_fields=["etat"])
        affectation = AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.CONTRIBUTEUR,
        )

        self.assertFalse(affectation.est_active())
        affectation.acces_historique = True
        affectation.save(update_fields=["acces_historique"])
        self.assertTrue(affectation.est_active())

    def test_affectation_inter_ecoles_refusee(self):
        autre_ecole = Ecole.objects.create(nom="Ailleurs")
        autre_classe = Classe.objects.create(ecole=autre_ecole, nom="GS")

        with self.assertRaises(ValidationError):
            AffectationClasse.objects.create(
                appartenance=self.appartenance,
                classe=autre_classe,
                type=AffectationClasse.RESPONSABLE,
            )

    def test_niveaux_simultanes_refuses(self):
        AffectationClasse.objects.create(
            appartenance=self.appartenance,
            classe=self.classe,
            type=AffectationClasse.RESPONSABLE,
        )

        with self.assertRaises(ValidationError):
            AffectationClasse.objects.create(
                appartenance=self.appartenance,
                classe=self.classe,
                type=AffectationClasse.CONTRIBUTEUR,
            )

    def test_classe_en_preparation_sans_responsable(self):
        self.assertEqual(self.classe.etat, Classe.PREPARATION)
        with self.assertRaises(ValidationError):
            self.classe.activer()

        self.classe.etat = Classe.ACTIVE
        with self.assertRaises(ValidationError):
            self.classe.save()

    def test_les_adresses_non_vides_sont_uniques_sans_tenir_compte_de_la_casse(self):
        Utilisateur = get_user_model()
        Utilisateur.objects.create_user("premier", "unique@example.test")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Utilisateur.objects.create_user("second", "UNIQUE@example.test")

        Utilisateur.objects.create_user("sans-email-1", "")
        Utilisateur.objects.create_user("sans-email-2", "")

    def test_activation_avec_plusieurs_responsables(self):
        autre = get_user_model().objects.create_user("bob")
        autre_appartenance = AppartenanceEcole.objects.create(
            utilisateur=autre,
            ecole=self.ecole,
        )
        for appartenance in (self.appartenance, autre_appartenance):
            AffectationClasse.objects.create(
                appartenance=appartenance,
                classe=self.classe,
                type=AffectationClasse.RESPONSABLE,
            )

        self.classe.activer()

        self.assertEqual(self.classe.etat, Classe.ACTIVE)
        self.assertEqual(self.classe.responsables_actifs().count(), 2)

    def test_direction_reste_distincte_d_une_affectation(self):
        ResponsabiliteEcole.objects.create(
            appartenance=self.appartenance,
            type=ResponsabiliteEcole.DIRECTION,
        )

        self.assertEqual(self.appartenance.responsabilites.count(), 1)
        self.assertFalse(self.appartenance.affectations_classes.exists())
