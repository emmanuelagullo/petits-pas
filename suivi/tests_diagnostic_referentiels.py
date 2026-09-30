import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .models import Competence, Domaine, Ecole, Observation, Scolarite
from .tests import Base


class DiagnosticReferentiels(Base):
    def rapport(self, **options):
        sortie = StringIO()
        call_command("diagnostiquer_referentiels", json=True, stdout=sortie, **options)
        return json.loads(sortie.getvalue())

    def test_lecture_seule_et_rapport_sans_identite_enfant(self):
        self.creer_trace(commentaire="Commentaire privé fictif")
        with CaptureQueriesContext(connection) as requetes:
            rapport = self.rapport()
        self.assertTrue(rapport["lecture_seule"])
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in requetes))
        self.assertNotIn("Commentaire privé", json.dumps(rapport))
        self.assertNotIn(self.eleve.prenom, json.dumps(rapport))
        self.assertEqual(rapport["ecoles"][0]["volumes"]["traces"], 1)

    def test_doublon_bloquant_et_masquage_conserve(self):
        Competence.objects.create(domaine=self.competence.domaine, code=self.competence.code, libelle="Autre")
        self.creer_trace()
        Competence.objects.filter(pk=self.competence.pk).update(active=False)
        codes = {c["code"] for c in self.rapport()["ecoles"][0]["constats"]}
        self.assertIn("codes_doublons_dans_domaine", codes)
        self.assertIn("competence_masquee_avec_observations", codes)
        with self.assertRaises(CommandError):
            self.rapport(exiger_coherent=True)
        self.competence.refresh_from_db()
        self.assertFalse(self.competence.active)

    def test_etat_multi_annees_a_examiner_sans_echec(self):
        self.creer_trace()
        from .models import Classe
        ancienne = Classe.objects.create(ecole=self.ecole, nom="Ancienne", annee_scolaire="2020-2021")
        Scolarite.objects.create(eleve=self.eleve, classe=ancienne, annee_scolaire="2020-2021", niveau="PS")
        rapport = self.rapport(exiger_coherent=True)
        self.assertIn("etat_sans_annee_unique", {c["code"] for c in rapport["ecoles"][0]["constats"]})

    def test_sous_domaine_et_annee_invalides(self):
        from .models import SousDomaine
        autre = Domaine.objects.create(ecole=self.ecole, code="AUTRE", nom="Autre")
        sous = SousDomaine.objects.create(domaine=autre, code="S", nom="Sous-domaine")
        Competence.objects.filter(pk=self.competence.pk).update(sous_domaine=sous)
        from .models import Classe
        Classe.objects.filter(pk=self.classe.pk).update(annee_scolaire="invalide")
        codes = {c["code"] for c in self.rapport()["ecoles"][0]["constats"]}
        self.assertIn("competence_sous_domaine_incoherent", codes)
        self.assertIn("classe_annee_invalide", codes)

    def test_reglage_et_formulation_origine_incoherents(self):
        from .models import FormulationLocale, FormulationProposee, ReglagePresentation
        autre = Ecole.objects.create(nom="École fictive B")
        ReglagePresentation.objects.create(ecole=autre, competence=self.competence)
        source = FormulationProposee.objects.create(competence=self.competence, code="F", texte="Texte")
        domaine = Domaine.objects.create(ecole=self.ecole, code="AUTRE", nom="Autre")
        competence = Competence.objects.create(domaine=domaine, code="X", libelle="Autre")
        FormulationLocale.objects.create(ecole=self.ecole, competence=competence, origine=source, texte="Local")
        codes = {c["code"] for e in self.rapport()["ecoles"] for c in e["constats"]}
        self.assertIn("reglage_presentation_incoherent", codes)
        self.assertIn("formulation_locale_incoherente", codes)

    def test_isolation_et_incoherence_ecole(self):
        autre = Ecole.objects.create(nom="Autre école fictive")
        domaine = Domaine.objects.create(ecole=autre, code="LANG", nom="Langage")
        competence = Competence.objects.create(domaine=domaine, code="X", libelle="Autre")
        Observation.objects.create(eleve=self.eleve, competence=competence)
        rapport = self.rapport(ecole=self.ecole.pk)
        self.assertEqual(len(rapport["ecoles"]), 1)
        self.assertIn("observation_autre_ecole", {c["code"] for c in rapport["ecoles"][0]["constats"]})
        with self.assertRaises(CommandError):
            self.rapport(ecole=999999)


class DiagnosticVide(TestCase):
    def test_base_vide(self):
        sortie = StringIO()
        call_command("diagnostiquer_referentiels", json=True, exiger_coherent=True, stdout=sortie)
        self.assertEqual(json.loads(sortie.getvalue())["ecoles"], [])
