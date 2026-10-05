from io import BytesIO
from unittest import TestCase

from PIL import Image

from .services.medias import (
    ImagePriveeInvalide,
    POLITIQUE_EQUILIBREE,
    PolitiqueImages,
    normaliser_image,
)


def image_test(taille=(2400, 1600), *, format="JPEG", orientation=None, transparente=False):
    mode = "RGBA" if transparente else "RGB"
    couleur = (40, 120, 200, 100) if transparente else (40, 120, 200)
    image = Image.new(mode, taille, couleur)
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    exif[315] = "Métadonnée privée fictive"
    sortie = BytesIO()
    image.save(sortie, format, exif=exif)
    return sortie.getvalue()


class NormalisationImagesPrivees(TestCase):
    def test_trace_corrige_orientation_limite_dimensions_et_supprime_exif(self):
        resultat = normaliser_image(image_test((1200, 1800), orientation=6))

        self.assertEqual((resultat.largeur, resultat.hauteur), (1600, 1067))
        self.assertEqual(resultat.format, "JPEG")
        with Image.open(BytesIO(resultat.contenu)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.getexif(), {})
            self.assertEqual(image.info.get("icc_profile"), None)

    def test_couverture_conserve_une_dimension_superieure_a_la_trace(self):
        source = image_test((3000, 2000))

        trace = normaliser_image(source, famille="trace")
        couverture = normaliser_image(source, famille="couverture")

        self.assertEqual((trace.largeur, trace.hauteur), (1600, 1067))
        self.assertEqual((couverture.largeur, couverture.hauteur), (2400, 1600))

    def test_variante_pdf_est_plus_petite_et_repart_de_la_source(self):
        source = image_test((2400, 1600))
        principale = normaliser_image(source)
        pdf = normaliser_image(source, variante="pdf")

        self.assertEqual((pdf.largeur, pdf.hauteur), (600, 400))
        self.assertLess(len(pdf.contenu), len(principale.contenu))

    def test_transparence_est_aplatie_sur_fond_blanc(self):
        resultat = normaliser_image(image_test(format="PNG", transparente=True))

        with Image.open(BytesIO(resultat.contenu)) as image:
            self.assertEqual(image.mode, "RGB")
            # Le bleu semi-transparent est composé avec un fond blanc.
            rouge, vert, bleu = image.getpixel((0, 0))
            self.assertGreater(rouge, 100)
            self.assertGreater(vert, 120)
            self.assertGreater(bleu, 200)

    def test_refuse_fichier_invalide_vide_trop_lourd_ou_trop_grand(self):
        with self.assertRaisesRegex(ImagePriveeInvalide, "n’est pas une image"):
            normaliser_image(b"pas une image")
        with self.assertRaisesRegex(ImagePriveeInvalide, "vide"):
            normaliser_image(b"")

        politique = PolitiqueImages(
            limite_brute_octets=8,
            limite_pixels=100,
            trace_principale=POLITIQUE_EQUILIBREE.trace_principale,
            trace_pdf=POLITIQUE_EQUILIBREE.trace_pdf,
            couverture_principale=POLITIQUE_EQUILIBREE.couverture_principale,
            couverture_pdf=POLITIQUE_EQUILIBREE.couverture_pdf,
        )
        with self.assertRaisesRegex(ImagePriveeInvalide, "volumineuse"):
            normaliser_image(b"012345678", politique=politique)

        politique = PolitiqueImages(
            limite_brute_octets=POLITIQUE_EQUILIBREE.limite_brute_octets,
            limite_pixels=100,
            trace_principale=POLITIQUE_EQUILIBREE.trace_principale,
            trace_pdf=POLITIQUE_EQUILIBREE.trace_pdf,
            couverture_principale=POLITIQUE_EQUILIBREE.couverture_principale,
            couverture_pdf=POLITIQUE_EQUILIBREE.couverture_pdf,
        )
        with self.assertRaisesRegex(ImagePriveeInvalide, "trop de pixels"):
            normaliser_image(image_test((20, 20)), politique=politique)

    def test_refuse_un_format_image_non_pris_en_charge(self):
        source = image_test(format="BMP")
        with self.assertRaisesRegex(ImagePriveeInvalide, "JPEG, PNG ou WebP"):
            normaliser_image(source)

    def test_parametres_inconnus_sont_des_erreurs_de_programmation(self):
        with self.assertRaises(ValueError):
            normaliser_image(image_test(), famille="inconnue")
        with self.assertRaises(ValueError):
            normaliser_image(image_test(), variante="inconnue")
