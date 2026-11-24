from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from .noms_archives import enregistrer_nom_zip, nom_zip, relire_nom_zip


class NomsArchivesTests(SimpleTestCase):
    def test_nom_normalise_et_repere_stable(self):
        date = datetime(2026, 11, 25, 12, 30, 52, tzinfo=timezone.utc)
        self.assertEqual(nom_zip("classe", "École des Tilleuls", "MS_GS !", "2026-2027", date=date),
                         "petits-pas-classe-ecole-des-tilleuls-ms-gs-2026-2027-2026-11-25-123052.zip")
        self.assertEqual(nom_zip("référentiel", "L’écrit", edition="2.1"),
                         "petits-pas-referentiel-lecrit-edition-2-1.zip")

    def test_nom_prepare_et_compatibilite_du_stock_preexistant(self):
        with TemporaryDirectory() as dossier:
            destination = Path(dossier)
            secours = "petits-pas-ecole-secours.zip"
            nom = "petits-pas-ecole-ancien-nom.zip"
            self.assertEqual(relire_nom_zip(destination, secours), secours)
            enregistrer_nom_zip(destination, nom)
            self.assertEqual(relire_nom_zip(destination, secours), nom)
