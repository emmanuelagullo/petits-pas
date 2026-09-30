from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from .models import (AdoptionReferentiel, EtatAnnuelObservation, ReferentielAnnuel,
                     SourceReferentiel, UsageCompetence, VersionReferentiel)
from .tests import Base


class FondationsReferentiels(Base):
    def setUp(self):
        super().setUp()
        source = SourceReferentiel.objects.create(identifiant="fictive", titre="Base fictive", ecole=self.ecole)
        self.version = VersionReferentiel.objects.create(source=source, numero="initial", empreinte="a" * 64, contenu={})
        self.annuel = ReferentielAnnuel.objects.create(ecole=self.ecole, annee_scolaire=self.classe.annee_scolaire, version_proposee=self.version)
        self.adoption = AdoptionReferentiel.objects.create(classe=self.classe, annuel=self.annuel, version=self.version)
        self.usage = UsageCompetence.objects.create(adoption=self.adoption, competence=self.competence, cle_definition="locale-1")

    def test_version_non_modifiable(self):
        self.version.contenu = {"modifie": True}
        with self.assertRaises(ValidationError):
            self.version.save()
        self.version.refresh_from_db()
        self.assertEqual(self.version.contenu, {})

    def test_une_adoption_courante_et_usages_uniques(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AdoptionReferentiel.objects.create(classe=self.classe, annuel=self.annuel, version=self.version)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsageCompetence.objects.create(adoption=self.adoption, competence=self.competence, cle_definition="autre")
        self.adoption.courante = False
        self.adoption.save()
        AdoptionReferentiel.objects.create(classe=self.classe, annuel=self.annuel, version=self.version)

    def test_etat_inconnu_et_annee_coherente(self):
        trace = self.creer_trace()
        etat = EtatAnnuelObservation(observation=trace.observation, usage=self.usage,
                                    annee_scolaire=self.classe.annee_scolaire)
        etat.full_clean()
        etat.statut = "reussi"
        with self.assertRaises(ValidationError):
            etat.full_clean()
        etat.connu = True
        etat.annee_scolaire = "2000-2001"
        with self.assertRaises(ValidationError):
            etat.full_clean()

    def test_observations_et_contextes_proteges(self):
        trace = self.creer_trace()
        trace.usage_referentiel = self.usage
        trace.save()
        with self.assertRaises(ProtectedError):
            self.usage.delete()
        with self.assertRaises(ProtectedError):
            self.competence.delete()
        with self.assertRaises(ProtectedError):
            self.version.delete()


class RepriseReferentiels(Base):
    def test_reprise_idempotente_sans_reussites_antidatees(self):
        from .services.reprise_referentiels import reprendre
        trace = self.creer_trace(commentaire="Trace fictive")
        statut = trace.observation.statut
        self.assertTrue(reprendre(self.ecole.pk))
        trace.refresh_from_db()
        self.assertIsNotNone(trace.usage_referentiel_id)
        self.assertEqual(trace.commentaire, "Trace fictive")
        trace.observation.refresh_from_db()
        self.assertEqual(trace.observation.statut, statut)
        self.assertFalse(EtatAnnuelObservation.objects.get(observation=trace.observation).connu)
        self.assertIsNone(EtatAnnuelObservation.objects.get(observation=trace.observation).statut)
        nombres = (UsageCompetence.objects.count(), VersionReferentiel.objects.count())
        self.assertFalse(reprendre(self.ecole.pk))
        self.assertEqual(nombres, (UsageCompetence.objects.count(), VersionReferentiel.objects.count()))

    def test_blocage_atomique_sur_doublon(self):
        from django.core.management.base import CommandError
        from .models import Competence
        from .services.reprise_referentiels import reprendre
        Competence.objects.create(domaine=self.competence.domaine, code=self.competence.code, libelle="Doublon")
        with self.assertRaises(CommandError):
            reprendre(self.ecole.pk)
        self.assertEqual(SourceReferentiel.objects.count(), 0)

    def test_confirmation_copie_et_ecole_absente(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("reprendre_referentiels", ecole=self.ecole.pk)
        with self.assertRaises(CommandError):
            call_command("reprendre_referentiels", ecole=999999, appliquer_sur_copie=True)
