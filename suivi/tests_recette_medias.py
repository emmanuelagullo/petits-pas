import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image


CHEMIN_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generer-images-recette.py"
SPEC = importlib.util.spec_from_file_location("generer_images_recette", CHEMIN_SCRIPT)
GENERATEUR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATEUR)

CHEMIN_RECETTE = Path(__file__).resolve().parents[1] / "scripts" / "recetter-medias-pdf.py"
SPEC_RECETTE = importlib.util.spec_from_file_location("recetter_medias_pdf", CHEMIN_RECETTE)
RECETTE = importlib.util.module_from_spec(SPEC_RECETTE)
SPEC_RECETTE.loader.exec_module(RECETTE)


class GenerateurImagesRecette(TestCase):
    def test_genere_des_images_fictives_deterministes_et_les_cas_limites(self):
        with TemporaryDirectory() as premier, TemporaryDirectory() as second:
            manifeste_1 = GENERATEUR.generer(premier)
            manifeste_2 = GENERATEUR.generer(second)

            self.assertEqual(manifeste_1, manifeste_2)
            self.assertEqual(manifeste_1["format"], "petits-pas-recette-medias")
            self.assertEqual(len(manifeste_1["images"]), 19)
            self.assertEqual(
                {entree["role"] for entree in manifeste_1["images"]},
                {"trace", "couverture", "illustration", "invalide"},
            )

            images = {entree["fichier"]: entree for entree in manifeste_1["images"]}
            self.assertEqual(images["trace-02.jpg"]["orientation_exif"], 6)
            self.assertEqual(images["couverture-ecole-classe.jpg"]["largeur"], 3600)
            self.assertIsNone(images["image-invalide.jpg"]["format"])

            with Image.open(Path(premier) / "trace-01.jpg") as image:
                self.assertEqual(image.getexif().get(315), "Personne fictive")
            with Image.open(Path(premier) / "illustration-transparente.png") as image:
                self.assertEqual(image.mode, "RGBA")

            manifeste_disque = json.loads((Path(premier) / "manifest.json").read_text())
            self.assertEqual(manifeste_disque, manifeste_1)

    def test_produit_un_rapport_et_des_pdf_mesurables(self):
        with TemporaryDirectory() as temporaire:
            destination = Path(temporaire)
            images = destination / "images"
            GENERATEUR.generer(images)
            configurations = {
                "sans-photo": {"traces": []},
                "une-photo": {"traces": [images / "trace-01.jpg"]},
            }

            rapport = RECETTE.recetter(destination, pages=3, configurations=configurations)

            self.assertEqual([r["scenario"] for r in rapport["resultats"]],
                             ["sans-photo", "une-photo"])
            self.assertTrue(all(r["pages"] == 3 for r in rapport["resultats"]))
            self.assertGreater(rapport["resultats"][1]["octets_entree"], 0)
            for resultat in rapport["resultats"]:
                self.assertEqual(resultat["avertissements_weasyprint"], [])
                pdf = destination / resultat["pdf"]
                self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))
                self.assertEqual(pdf.stat().st_size, resultat["octets_pdf"])
            self.assertTrue((destination / "rapport.json").is_file())
