import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .services.catalogues_externes import CATALOGUE_DEMONSTRATION, edition_grist, lire_catalogue_grist
from .services.import_sources_referentiels import lire_source
from .services.publications_grist import contenu_grist, meme_contenu_grist, publier_edition_grist


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
            if not any(all(ligne_existante.get(cle) == valeur for cle, valeur in ligne["require"].items())
                       for ligne_existante in lignes):
                lignes.append({**ligne["require"], **ligne["fields"]})
            raise ValidationError("Réponse perdue")

        def lire(prefixe, identifiant, chemin=""):
            if not chemin:
                return {"name": "Document fictif", "id": identifiant}
            if chemin == "/tables":
                return {"tables": [{"id": "Editions"}, {"id": "PetitsPasEspace"}]}
            if chemin == "/tables/PetitsPasEspace/records":
                return {"records": [{"fields": {"Identifiant": "espace", "Nom": "Espace fictif"}},
                                    {"fields": {"Identifiant": "catalogue", "Nom": "Catalogue fictif"}}]}
            self.assertEqual(chemin, "/tables/Editions/records")
            return {"records": [{"fields": ligne} for ligne in lignes]}

        destination = {"url": CATALOGUE_DEMONSTRATION}
        with patch("suivi.services.publications_grist.requete_api", side_effect=mettre), patch(
                "suivi.services.publications_grist.lire_api", side_effect=lire), patch(
                "suivi.services.catalogues_externes.lire_api", side_effect=lire):
            publier_edition_grist(destination, "langage-test", "Langage", 1, document)
            publier_edition_grist(destination, "langage-test", "Langage", 1, document)
            publier_edition_grist(destination, "autre-reference", "Autre titre", 1, document)
            with self.assertRaisesMessage(ValidationError, "Ce numéro est déjà utilisé"):
                publier_edition_grist(destination, "langage-test", "Langage", 1, {**document, "domaines": []})
            autre, _ = lire_source(edition_grist(CATALOGUE_DEMONSTRATION, "autre-reference", 1))
            self.assertEqual(autre["source"]["titre"], "Autre titre")
            catalogue = lire_catalogue_grist(CATALOGUE_DEMONSTRATION)
            self.assertEqual(catalogue["nom"], "Catalogue fictif")
            self.assertEqual([r["editions"] for r in catalogue["referentiels"]], [[1], [1]])
            recu, _ = lire_source(edition_grist(CATALOGUE_DEMONSTRATION, "langage-test", 1))
        self.assertEqual(recu["domaines"][0]["sous_domaines"][0]["competences"][0]["identite"], "identite-stable")
        self.assertEqual(recu["source"]["licence"], "CC0-1.0")
        edition = {"Contenu": contenu_grist(document)}
        self.assertTrue(meme_contenu_grist(edition, {**document, "version": "5"}))
        self.assertFalse(meme_contenu_grist(edition, {**document, "domaines": []}))

    def test_un_document_vierge_est_prepare_seulement_pour_publier(self):
        from .services.publications_grist import destination_grist

        colonnes = {"columns": [{"id": nom, "fields": {"type": type_colonne}} for nom, type_colonne in (
            ("Numero", "Int"), ("Referentiel", "Text"), ("Titre", "Text"), ("Contenu", "Text"),
        )]}
        reponses = {
            "/tables": {"tables": [{"id": "Table1"}]},
            "/tables/Table1/records?limit=1": {"records": []},
            "/tables/Editions/columns": colonnes,
            "/tables/Editions/records": {"records": []},
        }
        with patch("suivi.services.publications_grist.document_grist", return_value=(
                "/o/docs", "exemple", CATALOGUE_DEMONSTRATION, "Document de test",
        )), patch("suivi.services.publications_grist.lire_api", side_effect=lambda p, d, c: reponses[c]), patch(
                "suivi.services.publications_grist.requete_api") as ecrire:
            with self.assertRaises(ValidationError):
                destination_grist(CATALOGUE_DEMONSTRATION)
            ecrire.assert_not_called()
            self.assertEqual(destination_grist(CATALOGUE_DEMONSTRATION, preparer_vierge=True)["editions"], [])
            self.assertEqual(ecrire.call_args.kwargs["methode"], "POST")
            reponses["/tables/Table1/records?limit=1"] = {"records": [{"fields": {"A": "Donnée existante"}}]}
            ecrire.reset_mock()
            with self.assertRaises(ValidationError):
                destination_grist(CATALOGUE_DEMONSTRATION, preparer_vierge=True)
            ecrire.assert_not_called()

    def test_mode_icones_masque_les_editions_sans_les_effacer(self):
        from .services.catalogues_externes import lire_catalogue_grist

        edition = {"Numero": 1, "Referentiel": "source", "Titre": "Source", "Contenu": "{}"}
        mode = {"Identifiant": "mode-contenu", "Nom": "icones"}

        def api(prefixe, document, chemin=""):
            if chemin == "/tables":
                return {"tables": [{"id": "Editions"}, {"id": "PetitsPasEspace"}]}
            if chemin == "/tables/Editions/records":
                return {"records": [{"fields": edition}]}
            if chemin == "/tables/PetitsPasEspace/records":
                return {"records": [{"fields": mode}]}
            return {"name": "Catalogue", "id": document}

        with patch("suivi.services.catalogues_externes.lire_api", side_effect=api):
            masque, lignes = lire_catalogue_grist(CATALOGUE_DEMONSTRATION, avec_lignes=True)
            self.assertEqual(masque["referentiels"], [])
            self.assertEqual(lignes, [edition])
            mode["Nom"] = "complet"
            self.assertEqual(lire_catalogue_grist(CATALOGUE_DEMONSTRATION)["referentiels"][0]["editions"], [1])

    def test_initialisation_du_nom_sans_ecraser_le_nom_partage(self):
        from .services.catalogues_externes import enregistrer_nom_catalogue_grist

        reponses = {
            "/tables": {"tables": [{"id": "Editions"}, {"id": "PetitsPasEspace"}]},
            "/tables/PetitsPasEspace/records": {
                "records": [{"fields": {"Identifiant": "catalogue", "Nom": "Nom partagé"}}],
            },
        }
        module = "suivi.services.catalogues_externes."
        with patch(module + "lire_api", side_effect=lambda p, d, chemin: reponses[chemin]), patch(
                module + "requete_api") as ecrire:
            self.assertEqual(enregistrer_nom_catalogue_grist(CATALOGUE_DEMONSTRATION, "Proposition"),
                             "Nom partagé")
        self.assertIn("noupdate=true", ecrire.call_args.args[2])
        self.assertEqual(json.loads(ecrire.call_args.kwargs["corps"])["records"][0]["require"],
                         {"Identifiant": "catalogue"})

    def test_icone_deja_presente_reutilisee_et_empreinte_verifiee(self):
        from base64 import b64encode
        from io import BytesIO

        from PIL import Image

        from .icones_partagees import empreinte_png
        from .services.publications_grist import publier_icones_grist

        fichier = BytesIO()
        Image.new("RGBA", (2, 2), "red").save(fichier, format="PNG")
        png = fichier.getvalue()
        empreinte = empreinte_png(png)
        cible = "suivi.services.catalogues_externes.lire_api"
        lignes = {"records": [{"fields": {"Empreinte": empreinte, "PNG": b64encode(png).decode("ascii")}}]}
        with patch("suivi.services.publications_grist.tables_grist", return_value={"PetitsPasIcones"}), patch(
                cible, return_value=lignes), patch("suivi.services.publications_grist.requete_api") as ecrire:
            publier_icones_grist("/o/docs", "document-fictif", {empreinte: png})
            ecrire.assert_not_called()
            lignes["records"][0]["fields"]["PNG"] = "invalide"
            with self.assertRaises(ValidationError):
                publier_icones_grist("/o/docs", "document-fictif", {empreinte: png})
            ecrire.assert_not_called()

    def test_un_espace_de_partage_peut_recevoir_la_table_editions(self):
        from .services.publications_grist import document_preparable

        tables = {"PetitsPasEspace", "PetitsPasClasses", "PetitsPasContenus", "PetitsPasContributions"}
        self.assertTrue(document_preparable("/o/docs", "fictif", tables))
        self.assertFalse(document_preparable("/o/docs", "fictif", tables | {"Registre"}))
        with patch("suivi.services.publications_grist.lire_api", return_value={"records": []}):
            self.assertTrue(document_preparable("/o/docs", "fictif", tables | {"Table1"}))
