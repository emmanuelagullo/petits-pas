from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from .models import (AdoptionReferentiel, DefinitionSourceCompetence, IdentiteSourceCompetence,
                     Observation, SourceReferentiel, Trace, VersionReferentiel)
from .services.import_sources_referentiels import importer_source
from .services.reprise_referentiels import reprendre
from .tests import Base


def document(source="fictive-a", version="1"):
    return {"format": 1, "source": {"identifiant": source, "titre": "Progression fictive",
            "provenance": "Exemple de test, sans portée officielle", "licence": "CC-BY-SA-4.0", "provisoire": True},
            "version": version, "domaines": [{"code": "LANG", "nom": "Langage",
            "competences": [{"identite": "oser-parler", "code": "L01", "libelle": "Je parle", "niveau": "PS"}]}]}


def importer(doc, **options):
    return importer_source(yaml.safe_dump(doc, allow_unicode=True), **options)


class ImportSources(TestCase):
    def test_coexistence_sans_equivalence_par_code_ou_libelle(self):
        a, cree, nombre = importer(document())
        b, _, _ = importer(document("fictive-b"))
        self.assertTrue(cree)
        self.assertEqual(nombre, 1)
        self.assertNotEqual(a.definitions.get().identite_id, b.definitions.get().identite_id)
        self.assertEqual(SourceReferentiel.objects.count(), 2)

    def test_nouvelle_version_retient_identite_et_ancienne_definition(self):
        ancienne, _, _ = importer(document())
        nouvelle = document(version="2")
        nouvelle["domaines"][0]["competences"][0].update(code="L-renomme", libelle="J'ose parler")
        version, _, _ = importer(nouvelle)
        self.assertEqual(ancienne.definitions.get().identite_id, version.definitions.get().identite_id)
        ancienne.refresh_from_db()
        self.assertEqual(ancienne.contenu["domaines"][0]["competences"][0]["libelle"], "Je parle")
        self.assertNotEqual(version.empreinte, ancienne.empreinte)

    def test_reimport_identique_et_empreinte_independante_ordre_cles(self):
        premiere, _, _ = importer(document())
        autre = dict(reversed(list(document().items())))
        retour, cree, _ = importer(autre)
        self.assertFalse(cree)
        self.assertEqual(retour.pk, premiere.pk)
        self.assertEqual(VersionReferentiel.objects.count(), 1)
        self.assertEqual(IdentiteSourceCompetence.objects.count(), 1)

    def test_nouvelle_identite_ne_reprend_pas_celle_du_meme_code(self):
        ancienne, _, _ = importer(document())
        doc = document(version="2")
        doc["domaines"][0]["competences"][0]["identite"] = "autre-apprentissage"
        nouvelle, _, _ = importer(doc)
        self.assertNotEqual(ancienne.definitions.get().identite_id, nouvelle.definitions.get().identite_id)

    def test_exemple_documente_valide_sans_ecriture(self):
        contenu = (Path(__file__).resolve().parent.parent / "referentiel/exemples/source-fictive.yaml").read_text(encoding="utf-8")
        _, _, nombre = importer_source(contenu, verifier_seulement=True)
        self.assertEqual(nombre, 2)
        self.assertFalse(SourceReferentiel.objects.exists())

    def test_meme_numero_modifie_refuse_sans_nouvelle_identite(self):
        premiere, _, _ = importer(document())
        autre = document()
        autre["domaines"][0]["competences"][0]["identite"] = "autre-sens"
        with self.assertRaises(ValidationError):
            importer(autre)
        self.assertEqual(IdentiteSourceCompetence.objects.count(), 1)
        premiere.refresh_from_db()
        self.assertEqual(premiere.contenu["domaines"][0]["competences"][0]["identite"], "oser-parler")

    def test_retrait_ne_supprime_pas_identite_et_retour_la_retrouve(self):
        doc = document()
        doc["domaines"][0]["competences"].append({"identite": "ecouter", "code": "L02", "libelle": "J'écoute"})
        premiere, _, _ = importer(doc)
        identite = premiere.definitions.get(identite__identifiant="ecouter").identite_id
        importer(document(version="2"))
        doc["version"] = "3"
        retour, _, _ = importer(doc)
        self.assertEqual(retour.definitions.get(identite__identifiant="ecouter").identite_id, identite)
        self.assertEqual(premiere.definitions.count(), 2)

    def test_structure_sous_domaine_attendu_et_ressources_facultatives(self):
        doc = document()
        domaine = doc["domaines"][0]
        competence = domaine.pop("competences")[0]
        competence.update(icone="parler", formulations=[{"code": "p1", "texte": "<prénom> prend la parole."}])
        domaine.update(attendus=[{"code": "a1", "texte": "Oser parler"}],
                       sous_domaines=[{"code": "oral", "nom": "Oral", "competences": [competence]}])
        version, _, _ = importer(doc)
        self.assertEqual(version.contenu["domaines"][0]["sous_domaines"][0]["competences"][0]["icone"], "parler")
        self.assertEqual(version.definitions.count(), 1)

    def test_erreurs_de_format_aucune_ecriture(self):
        for modification in ("identite_absente", "identite_double", "code_double", "icone", "niveau", "champ", "boolean", "longueur", "licence", "reserve"):
            with self.subTest(modification=modification):
                doc = document()
                c = doc["domaines"][0]["competences"][0]
                if modification == "identite_absente": del c["identite"]
                elif modification in ("identite_double", "code_double"):
                    autre = deepcopy(c)
                    autre["code" if modification == "identite_double" else "identite"] = "different"
                    doc["domaines"][0]["competences"].append(autre)
                elif modification == "icone": c["icone"] = "inconnue"
                elif modification == "niveau": c["niveau"] = "CP"
                elif modification == "champ": c["libelé"] = "Faute de frappe"
                elif modification == "boolean": doc["source"]["provisoire"] = "false"
                elif modification == "longueur": c["libelle"] = "a" * 301
                elif modification == "licence": del doc["source"]["licence"]
                elif modification == "reserve": doc["source"]["identifiant"] = "reprise-ecole-1"
                with self.assertRaises(ValidationError): importer(doc)
                self.assertFalse(SourceReferentiel.objects.exists())

    def test_yaml_invalide_et_cles_repetees(self):
        for contenu in ("domaines: [", "format: 1\nformat: 1", "!!python/object:os.system {}", "42", ""):
            with self.subTest(contenu=contenu), self.assertRaises(ValidationError):
                importer_source(contenu)
        self.assertFalse(SourceReferentiel.objects.exists())

    def test_conflit_de_provenance_et_verification_sans_ecriture(self):
        importer(document(), verifier_seulement=True)
        self.assertFalse(SourceReferentiel.objects.exists())
        importer(document())
        autre = document(version="2")
        autre["source"]["provenance"] = "Autre auteur"
        with self.assertRaises(ValidationError): importer(autre, verifier_seulement=True)
        self.assertEqual(VersionReferentiel.objects.count(), 1)

    def test_echec_ecriture_annule_import_entier(self):
        with patch.object(DefinitionSourceCompetence, "save", side_effect=IntegrityError("échec fictif")):
            with self.assertRaises(IntegrityError): importer(document())
        self.assertFalse(SourceReferentiel.objects.exists())
        self.assertFalse(IdentiteSourceCompetence.objects.exists())

    def test_commande_verifier_et_erreurs(self):
        with TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "fictive.yaml"
            fichier.write_text(yaml.safe_dump(document()), encoding="utf-8")
            sortie = StringIO()
            call_command("importer_source_referentiel", str(fichier), verifier=True, stdout=sortie)
            self.assertIn("Aucune écriture", sortie.getvalue())
            self.assertFalse(SourceReferentiel.objects.exists())
            call_command("importer_source_referentiel", str(fichier), stdout=StringIO())
            fichier.write_text("format: [", encoding="utf-8")
            with self.assertRaises(CommandError): call_command("importer_source_referentiel", str(fichier))

    def test_edition_composee_retrouve_identite_et_archive_transportable(self):
        from .services.paquets_referentiels import exporter_paquet, lire_paquet

        source, _, _ = importer(document())
        doc = document("composition")
        doc["format"] = 2
        competence = doc["domaines"][0]["competences"][0]
        competence.update(source_origine="fictive-a", icone="parler", libelle="Expression orale")
        composee, _, _ = importer(doc)
        self.assertEqual(composee.definitions.get().identite, source.definitions.get().identite)
        with TemporaryDirectory() as repertoire:
            chemin = Path(repertoire) / "edition.zip"
            chemin.write_bytes(exporter_paquet(composee))
            sortie = StringIO()
            call_command("importer_source_referentiel", str(chemin), stdout=sortie)
            self.assertIn("déjà présente", sortie.getvalue())
        self.assertEqual(lire_paquet(exporter_paquet(composee)).count("fictive-a"), 1)
        competence["source_origine"] = "inconnue"
        with self.assertRaisesMessage(ValidationError, "Identité d’origine inconnue"):
            importer({**doc, "version": "2"}, verifier_seulement=True)

    def test_selection_reutilise_la_reference_d_origine(self):
        from .services.paquets_referentiels import exporter_selection, lire_paquet
        from .services.import_sources_referentiels import importer_source

        origine, _, _ = importer(document())
        reference = origine.definitions.get().identite
        fichier = exporter_selection(origine, [reference.identifiant])
        selection, cree, nombre = importer_source(lire_paquet(fichier))
        self.assertTrue(cree)
        self.assertEqual(nombre, 1)
        self.assertEqual(selection.definitions.get().identite, reference)
        self.assertFalse(importer_source(lire_paquet(fichier))[1])
        with self.assertRaises(ValidationError):
            exporter_selection(origine, ["inconnue"])

    def test_catalogues_d_ecole_isoles_et_idempotents(self):
        from .models import Ecole
        from .services.choix_bases_referentiels import choix_bases

        a = Ecole.objects.create(nom="A")
        b = Ecole.objects.create(nom="B")
        fichier = yaml.safe_dump(document("edition-partagee"))
        version_a, cree, _ = importer_source(fichier, ecole=a)
        self.assertTrue(cree)
        self.assertEqual(importer_source(fichier, ecole=a)[:2], (version_a, False))
        self.assertNotIn(version_a, choix_bases(b, "2026-2027").versions)
        version_b, cree, _ = importer_source(fichier, ecole=b)
        self.assertTrue(cree)
        self.assertNotEqual(version_a.source_id, version_b.source_id)
        self.assertEqual(list(choix_bases(b, "2026-2027").versions), [version_b])
        self.assertFalse(SourceReferentiel.objects.filter(ecole__isnull=True).exists())

    def test_zip_et_revision_echanges_entre_deux_ecoles(self):
        from .models import Ecole
        from .services.paquets_referentiels import exporter_paquet, lire_paquet
        from .views_paquets_referentiels import apercu_document

        origine = Ecole.objects.create(nom="École émettrice fictive")
        destination = Ecole.objects.create(nom="École destinataire fictive")
        recue = None
        for numero, libelle, icone in (("1", "Je parle", "parler"), ("2", "Je prends la parole", "livre")):
            source = document("edition-partagee", numero)
            source["domaines"][0]["competences"][0].update(libelle=libelle, icone=icone)
            edition = importer(source, ecole=origine)[0]
            contenu = lire_paquet(exporter_paquet(edition))
            apercu = apercu_document(contenu, destination)
            self.assertEqual(apercu["apercu"]["source"]["licence"], "CC-BY-SA-4.0")
            self.assertTrue(apercu["icones_importees"][0]["credit"])
            if recue:
                self.assertEqual(apercu["edition_comparee"], "1")
                self.assertTrue(apercu["comparaison_import"]["modifications"])
            nouvelle, cree, _ = importer_source(contenu, ecole=destination)
            self.assertTrue(cree)
            self.assertNotEqual(edition.source_id, nouvelle.source_id)
            self.assertEqual(importer_source(contenu, ecole=destination)[:2], (nouvelle, False))
            if recue:
                self.assertEqual(recue.definitions.get().identite_id, nouvelle.definitions.get().identite_id)
            recue = nouvelle

    def test_selection_scoped_cree_une_origine_locale_puis_la_retrouve(self):
        from .models import Ecole

        ecole = Ecole.objects.create(nom="Destination fictive")
        doc = document("selection")
        doc["format"] = 2
        doc["domaines"][0]["competences"][0]["source_origine"] = "nouvelle-origine"
        selection, _, _ = importer(doc, ecole=ecole)
        identite = selection.definitions.get().identite
        self.assertEqual(identite.source.ecole_id, ecole.pk)
        origine, _, _ = importer(document("nouvelle-origine"), ecole=ecole)
        self.assertEqual(origine.definitions.get().identite, identite)

    def test_definition_autre_source_refusee(self):
        a, _, _ = importer(document())
        b, _, _ = importer(document("fictive-b"))
        with self.assertRaises(ValidationError):
            DefinitionSourceCompetence(version=a, identite=b.definitions.get().identite).full_clean()


class ImportSansChangementDuSuivi(Base):
    def test_projection_composee_reutilise_competence_et_phrase(self):
        from .services.versions_sources_ecoles import definir_version_ecole

        doc = document()
        doc["domaines"][0]["competences"][0]["formulations"] = [{"code": "p1", "texte": "Je parle."}]
        origine, _, _ = importer(doc)
        avant = definir_version_ecole(self.ecole, origine)
        doc["source"] = {**doc["source"], "identifiant": "composition"}
        doc["format"] = 2
        doc["domaines"][0]["competences"][0].update(source_origine="fictive-a", code="C01")
        edition, _, _ = importer(doc)
        apres = definir_version_ecole(self.ecole, edition)
        self.assertEqual(avant["competences"][0]["id"], apres["competences"][0]["id"])
        self.assertEqual(avant["formulations"][0]["id"], apres["formulations"][0]["id"])

    def test_import_conserve_adoption_observations_et_traces(self):
        self.creer_trace(commentaire="Trace fictive conservée")
        reprendre(self.ecole.pk)
        adoption = list(AdoptionReferentiel.objects.values())
        etats = list(Observation.objects.values())
        traces = list(Trace.objects.values())
        importer(document())
        self.assertEqual(list(AdoptionReferentiel.objects.values()), adoption)
        self.assertEqual(list(Observation.objects.values()), etats)
        self.assertEqual(list(Trace.objects.values()), traces)
