"""Contrôle de provenance et de présence locale des dessins distribués."""
import hashlib
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
import yaml

from .presentation import catalogue_icones


class CollectionImages(SimpleTestCase):
    def test_catalogue_openmoji_versionne_avec_auteurs_empreintes_et_licence(self):
        racine = settings.BASE_DIR
        manifeste = yaml.safe_load((racine / 'referentiel/images-proposees/collection-im5.yaml').read_text())
        self.assertEqual(manifeste['version'], '17.0.0')
        self.assertEqual(manifeste['commit'], 'f9fc506a3f913be9897ab0181d611d4c910a4104')
        self.assertTrue((racine / manifeste['licence_locale']).is_file())
        catalogue = catalogue_icones()
        images = manifeste['illustrations']
        self.assertEqual(len(images), 19)
        self.assertEqual(sum(e['nouvelle_im5'] for e in images), 10)
        self.assertEqual({e['identifiant'] for e in images},
                         {cle for cle, e in catalogue.items() if e.get('credit') == 'openmoji'})
        for e in images:
            with self.subTest(image=e['identifiant']):
                self.assertTrue(e['auteur'])
                self.assertEqual(e['licence'], 'CC-BY-SA-4.0')
                self.assertEqual(e['modifications'], 'Aucune')
                self.assertEqual(e['version'], manifeste['version'])
                self.assertEqual(e['commit'], manifeste['commit'])
                self.assertEqual(catalogue[e['identifiant']]['fichier'], e['fichier'])
                fichier = racine / 'referentiel/static' / e['fichier']
                self.assertEqual(hashlib.sha256(fichier.read_bytes()).hexdigest(), e['sha256'])
