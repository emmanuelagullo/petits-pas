import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .services.catalogues_externes import CATALOGUE_DEMONSTRATION, edition_grist
from .services.import_sources_referentiels import lire_source
from .services.publications_grist import publier_edition_grist


class PublicationsGrist(SimpleTestCase):
    def test_relire_une_publication_et_refuser_decraser_une_edition(self):
        lignes = []
        document = {
            "format": 2, "origine": "source_declaree", "version": "1",
            "source": {"identifiant": "langage-test", "titre": "Langage", "provenance": "Équipe de test",
                       "licence": "CC0-1.0", "provisoire": True},
            "domaines": [{"code": "D", "nom": "Domaine", "competences": [], "sous_domaines": [
                {"code": "S", "nom": "Sous-domaine", "competences": [
                    {"identite": "identite-stable", "code": "C2", "libelle": "Décrire une image",
                     "niveau": "GS", "formulations": [{"code": "F1", "texte": "Je décris une image."}]}
                ]}
            ]}],
        }

        def mettre(prefixe, identifiant, chemin, *, corps):
            self.assertIn("noupdate=true", chemin)
            ligne, = json.loads(corps)["records"]
            if not lignes:
                lignes.append({**ligne["require"], **ligne["fields"]})
            raise ValidationError("Réponse perdue")

        def lire(prefixe, identifiant, chemin=""):
            if not chemin:
                return {"name": "Document fictif", "id": identifiant}
            self.assertEqual(chemin, "/tables/Editions/records")
            return {"records": [{"fields": ligne} for ligne in lignes]}

        destination = {"url": CATALOGUE_DEMONSTRATION}
        with patch("suivi.services.publications_grist.requete_api", side_effect=mettre), patch(
                "suivi.services.publications_grist.lire_api", side_effect=lire), patch(
                "suivi.services.catalogues_externes.lire_api", side_effect=lire):
            publier_edition_grist(destination, "langage-test", "Langage", 1, document)
            publier_edition_grist(destination, "langage-test", "Langage", 1, document)
            with self.assertRaisesMessage(ValidationError, "Ce numéro est déjà utilisé"):
                publier_edition_grist(destination, "autre-reference", "Langage", 1, document)
            recu, _ = lire_source(edition_grist(CATALOGUE_DEMONSTRATION, "langage-test", 1))
        self.assertEqual(recu["domaines"][0]["sous_domaines"][0]["competences"][0]["identite"], "identite-stable")
        self.assertEqual(recu["source"]["licence"], "CC0-1.0")
