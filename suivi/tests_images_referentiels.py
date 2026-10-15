"""Garantir qu'une association d'image ne change pas le contenu pédagogique."""
from copy import deepcopy
import hashlib
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
import yaml

from .presentation import catalogue_icones
from .services.import_sources_referentiels import normaliser


def entrees(noeud):
    if isinstance(noeud, dict):
        if 'libelle' in noeud and 'code' in noeud:
            yield noeud
        for valeur in noeud.values():
            yield from entrees(valeur)
    elif isinstance(noeud, list):
        for valeur in noeud:
            yield from entrees(valeur)


class AssociationsImages(SimpleTestCase):
    def test_editions_seuls_version_et_images_changent(self):
        racine = settings.BASE_DIR / 'referentiel'
        manifeste = yaml.safe_load((racine / 'images-proposees/associations-im4.yaml').read_text())
        for actuel, ancien, nombre in (
                ('cycle1/objectifs-programmes.yaml', 'cycle1/editions/objectifs-programmes-2026.1.yaml', 426),
                ('chatdecole/tableaux-cycle1.yaml', 'chatdecole/editions/tableaux-cycle1-2026.1.yaml', 417)):
            with self.subTest(actuel=actuel):
                version = yaml.safe_load((racine / actuel).read_text())
                origine = yaml.safe_load((racine / ancien).read_text())
                normaliser(version)
                normaliser(origine)
                self.assertEqual(version['version'], '2026.2')
                self.assertEqual(len(list(entrees(version))), nombre)
                images = {e['identite']: e['icone'] for e in entrees(version) if e.get('icone')}
                self.assertEqual(len(images), 6)
                declarations = {e['identite']: e['image'] for e in manifeste['associations']
                    if e['source'] == version['source']['identifiant'] and e['version'] == version['version']}
                self.assertEqual(images, declarations)
                self.assertTrue(set(images.values()) <= catalogue_icones().keys())
                copie = deepcopy(version)
                copie['version'] = origine['version']
                for e in entrees(copie):
                    e.pop('icone', None)
                self.assertEqual(copie, origine)

    def test_echantillon_conserve_sources_et_identites_sans_filiation_deduite(self):
        racine = settings.BASE_DIR
        manifeste = yaml.safe_load((racine / 'referentiel/images-proposees/echantillon-im1.yaml').read_text())
        for association in manifeste['associations']:
            fichier = racine / association['fichier_referentiel']
            self.assertEqual(hashlib.sha256(fichier.read_bytes()).hexdigest(), association['empreinte_referentiel'])
            contenu = yaml.safe_load(fichier.read_text())
            entree = next(e for e in entrees(contenu) if e['code'] == association['code'])
            self.assertEqual(entree.get('identite'), association['identite'])
            self.assertEqual(entree['libelle'], association['libelle'])
