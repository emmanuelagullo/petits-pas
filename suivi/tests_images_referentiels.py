"""Garantir qu'une association d'image ne change pas le contenu pédagogique."""
from copy import deepcopy
import hashlib
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
import yaml

from .presentation import catalogue_icones
from .tests import Base
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
                ('cycle1/editions/objectifs-programmes-2026.2.yaml', 'cycle1/editions/objectifs-programmes-2026.1.yaml', 426),
                ('chatdecole/editions/tableaux-cycle1-2026.2.yaml', 'chatdecole/editions/tableaux-cycle1-2026.1.yaml', 417)):
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


class AssociationsIM6(SimpleTestCase):
    def test_editions_relecture_explicite_et_contenu_pedagogique_inchange(self):
        racine = settings.BASE_DIR
        manifeste = yaml.safe_load((racine / 'referentiel/images-proposees/associations-im6.yaml').read_text())
        collection = yaml.safe_load((racine / 'referentiel/images-proposees/collection-im5.yaml').read_text())
        locaux = {e['identifiant'] for e in collection['illustrations']
                  if e['usage_local_sans_association_automatique']}
        self.assertEqual(len(manifeste['associations']), 98)
        for version in manifeste['versions']:
            with self.subTest(source=version['source']):
                fichier = racine / version['fichier']
                precedent = racine / version['precedente']
                self.assertEqual(hashlib.sha256(fichier.read_bytes()).hexdigest(), version['sha256'])
                self.assertEqual(hashlib.sha256(precedent.read_bytes()).hexdigest(), version['sha256_precedente'])
                contenu = yaml.safe_load(fichier.read_text())
                avant = yaml.safe_load(precedent.read_text())
                normaliser(contenu)
                self.assertEqual(contenu['version'], '2026.3')
                self.assertEqual(contenu['source']['identifiant'], version['source'])
                images = {e['identite']: e['icone'] for e in entrees(contenu) if e.get('icone')}
                declarations = {e['identite']: e for e in manifeste['associations']
                                if e['source'] == version['source'] and e['version'] == '2026.3'}
                self.assertEqual(len(images), version['associations'])
                self.assertEqual(images, {cle: e['image'] for cle, e in declarations.items()})
                self.assertFalse(set(images.values()) & locaux)
                for e in entrees(contenu):
                    if e.get('icone'):
                        self.assertIn(e['icone'], catalogue_icones())
                        self.assertEqual(e['libelle'], declarations[e['identite']]['libelle'])
                        self.assertTrue(declarations[e['identite']]['raison'])
                        self.assertIn(declarations[e['identite']]['portee'], {'outil', 'support', 'activite'})
                copie = deepcopy(contenu)
                copie['version'] = avant['version']
                for e in entrees(copie):
                    e.pop('icone', None)
                for e in entrees(avant):
                    e.pop('icone', None)
                self.assertEqual(copie, avant)

    def test_retraits_d_images_sans_retrait_d_apprentissage(self):
        racine = settings.BASE_DIR / 'referentiel'
        manifeste = yaml.safe_load((racine / 'images-proposees/associations-im6.yaml').read_text())
        self.assertEqual(len(manifeste['retraits']), 6)
        avant = {e['identite']: e for e in entrees(yaml.safe_load(
            (racine / 'cycle1/editions/cycle1-etaye-2026.2.yaml').read_text()))}
        apres = {e['identite']: e for e in entrees(yaml.safe_load(
            (racine / 'cycle1/cycle1-etaye.yaml').read_text()))}
        self.assertEqual(set(avant), set(apres))
        for retrait in manifeste['retraits']:
            identite = retrait['identite']
            self.assertEqual(avant[identite]['icone'], retrait['image_precedente'])
            self.assertFalse(apres[identite].get('icone'))
            self.assertTrue(retrait['raison'])


class ImportEditionsIM6(Base):
    def test_import_versions_precedentes_et_nouvelles_sans_bascule_de_classe(self):
        from .models import AdoptionReferentiel, Observation, Trace
        from .services.import_sources_referentiels import importer_source
        from .services.reprise_referentiels import reprendre
        self.creer_trace(commentaire='Observation entièrement fictive à conserver')
        reprendre(self.ecole.pk)
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        observations = list(Observation.objects.values())
        traces = list(Trace.objects.values())
        racine = settings.BASE_DIR
        manifeste = yaml.safe_load((racine / 'referentiel/images-proposees/associations-im6.yaml').read_text())
        for entree in manifeste['versions']:
            avant = importer_source((racine / entree['precedente']).read_text())[0]
            contenu_avant = deepcopy(avant.contenu)
            apres = importer_source((racine / entree['fichier']).read_text())[0]
            avant.refresh_from_db()
            self.assertEqual(avant.contenu, contenu_avant)
            self.assertNotEqual(apres.pk, avant.pk)
            self.assertEqual(apres.source_id, avant.source_id)
            self.assertEqual((avant.numero, apres.numero), ('2026.2', '2026.3'))
        self.assertEqual(AdoptionReferentiel.objects.get(classe=self.classe, courante=True).pk, adoption.pk)
        self.assertEqual(list(Observation.objects.values()), observations)
        self.assertEqual(list(Trace.objects.values()), traces)
