"""Événements de publication : sélection sans réseau ni écriture distante."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('publication_programmes',Path(__file__).with_name('publier-paquets.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class PublicationAutomatiqueTests(unittest.TestCase):
    def evenement(self):
        return {'action':'completed','workflow_run':{'id':123,'head_repository':{'full_name':p.DEPOT},
            'conclusion':'success','status':'completed','event':'push','head_branch':'0.12.0',
            'path':p.WORKFLOW,'head_sha':'a'*40}}

    def test_tag_valide_et_reprise_main(self):
        self.assertEqual(p.selectionner_evenement(self.evenement(),'workflow_run','refs/heads/main'),('123','0.12.0'))
        self.assertEqual(p.selectionner_evenement({'inputs':{'run':'123','tag':'0.12.0'}},'workflow_dispatch','refs/heads/main'),('123','0.12.0'))

    def test_branches_pr_forks_echecs_ou_autre_workflow_ignores(self):
        for cle,valeur in [('head_branch','main'),('head_branch','branche-fictive'),
                           ('event','pull_request'),('event','workflow_dispatch'),
                           ('conclusion','failure'),('status','in_progress'),
                           ('head_repository',{'full_name':'fictif/fork'}),('path','.github/workflows/autre.yml')]:
            with self.subTest(cle=cle,valeur=valeur):
                e=self.evenement();e['workflow_run'][cle]=valeur
                self.assertIsNone(p.selectionner_evenement(e,'workflow_run','refs/heads/main'))

    def test_reprise_hors_main_et_injection_refusees(self):
        for reference,tag in [('refs/heads/fictif','0.12.0'),('refs/heads/main','0.12.0\ninjection=true')]:
            with self.assertRaises(ValueError):
                p.selectionner_evenement({'inputs':{'run':'123','tag':tag}},'workflow_dispatch',reference)

    def test_cli_selection_ecrit_seulement_des_sorties_bornees(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=root/'event.json';event.write_text(json.dumps(self.evenement()))
            sortie=root/'outputs'
            subprocess.run([sys.executable,str(Path(__file__).with_name('publier-paquets.py')),
                            '--selectionner-evenement',str(event)],check=True,
                env={**os.environ,'GITHUB_EVENT_NAME':'workflow_run','GITHUB_REF':'refs/heads/main','GITHUB_OUTPUT':str(sortie)})
            self.assertEqual(sortie.read_text(),'eligible=true\nrun=123\ntag=0.12.0\n')
