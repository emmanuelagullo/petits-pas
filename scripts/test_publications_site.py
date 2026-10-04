"""Le site n'annonce que des téléchargements de releases publiques."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('catalogue',Path(__file__).with_name('preparer-publications-site.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CatalogueTests(unittest.TestCase):
    def release(self):
        return {'tag_name':'0.8','published_at':'2026-10-05T00:00:00Z','draft':False,'assets':[
            {'name':'PetitsPas-Setup-0.8-x64.exe','size':10,'browser_download_url':'https://github.com/emmanuelagullo/petits-pas/releases/download/0.8/PetitsPas-Setup-0.8-x64.exe'}]}

    def test_candidat_et_brouillon_non_annonces(self):
        published=self.release();draft=self.release();draft['draft']=True
        candidate=self.release();candidate['published_at']=None
        versions=module.catalogue([published,draft,candidate])['versions']
        self.assertEqual(len(versions),1);self.assertIn('windows',versions[0])

    def test_fichier_sur_une_autre_origine_non_propose(self):
        release=self.release();release['assets'][0]['browser_download_url']='https://ailleurs-fictif.example/setup.exe'
        self.assertEqual(module.catalogue([release])['versions'],[])
