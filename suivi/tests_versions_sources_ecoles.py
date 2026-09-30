from django.core.exceptions import ValidationError
from django.db import IntegrityError
from unittest.mock import patch

from .models import Competence, CompetenceSourceEcole, Ecole, Observation, VersionSourceEcole
from .services.versions_sources_ecoles import definir_version_ecole
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class VersionsEcoles(Base):
    def setUp(self):
        super().setUp()
        self.version = importer(document("premiere-fictive"))[0]

    def test_identite_source_pas_rapprochee_du_code_local(self):
        doc = document()
        doc["domaines"][0]["competences"][0].update(code=self.competence.code, libelle=self.competence.libelle)
        version = importer(doc)[0]
        contenu = definir_version_ecole(self.ecole, version)
        self.assertNotEqual(contenu["competences"][0]["id"], self.competence.pk)
        self.assertEqual(Observation.objects.count(), 0)

    def test_reutilisation_et_conservation_definitions_anciennes(self):
        a = definir_version_ecole(self.ecole, self.version)
        doc = document("premiere-fictive", version="2")
        doc["domaines"][0]["nom"] = "Autre intitulé"
        doc["domaines"][0]["competences"][0].update(libelle="J'ose parler", icone="parler")
        b = definir_version_ecole(self.ecole, importer(doc)[0])
        self.assertEqual(a["competences"][0]["id"], b["competences"][0]["id"])
        self.assertEqual(a["competences"][0]["libelle"], "Je parle")
        self.assertEqual(definir_version_ecole(self.ecole, self.version), a)
        self.assertEqual(CompetenceSourceEcole.objects.count(), 1)
        self.assertEqual(VersionSourceEcole.objects.count(), 2)

    def test_sources_et_ecoles_ne_partagent_pas_identites_de_suivi(self):
        a = definir_version_ecole(self.ecole, self.version)
        b = definir_version_ecole(self.ecole, importer(document("autre-fictive"))[0])
        autre = Ecole.objects.create(nom="Autre école fictive")
        c = definir_version_ecole(autre, self.version)
        self.assertEqual(len({a["competences"][0]["id"], b["competences"][0]["id"], c["competences"][0]["id"]}), 3)

    def test_cache_immuable_et_echec_transactionnel(self):
        contenu = definir_version_ecole(self.ecole, self.version)
        cache = VersionSourceEcole.objects.get()
        cache.contenu = {}
        with self.assertRaises(ValidationError): cache.save()
        cache.refresh_from_db()
        self.assertEqual(cache.contenu, contenu)
        autre = importer(document("autre-fictive"))[0]
        nombre = Competence.objects.count()
        with patch.object(VersionSourceEcole, "save", side_effect=IntegrityError("échec fictif")):
            with self.assertRaises(IntegrityError): definir_version_ecole(self.ecole, autre)
        self.assertEqual(Competence.objects.count(), nombre)

    def test_base_reprise_autre_ecole_refusee(self):
        reprendre(self.ecole.pk)
        from .models import VersionReferentiel
        initiale = VersionReferentiel.objects.get(source__ecole=self.ecole)
        self.assertEqual(definir_version_ecole(self.ecole, initiale), initiale.contenu)
        with self.assertRaises(ValidationError):
            definir_version_ecole(Ecole.objects.create(nom="Autre fictive"), initiale)
