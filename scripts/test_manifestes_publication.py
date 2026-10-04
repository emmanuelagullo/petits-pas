"""Versions de candidat, notes du tag et refus d'artefacts altérés."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publication

SHA = 'a' * 40

class ManifestTests(unittest.TestCase):
    def test_tag_et_branche_sans_git(self):
        with patch.dict(os.environ, {'CI_COMMIT_SHA':SHA,'CI_COMMIT_TAG':'0.8'}, clear=True):
            self.assertEqual(publication.identity()['application_version'], '0.8')
        with patch.dict(os.environ, {'GITHUB_SHA':SHA,'GITHUB_REF_TYPE':'branch'}, clear=True):
            self.assertEqual(publication.identity()['application_version'], 'dev.aaaaaaaa')
        with patch.dict(os.environ, {'CI_COMMIT_SHA':SHA,'CI_COMMIT_TAG':'main'}, clear=True):
            with self.assertRaises(ValueError): publication.identity()

    def test_notes_du_tag_uniquement(self):
        text = '* À venir\n- futur\n* 0.8 — 2026-10-05\n** Corrections\n- fichier =ZIP=\n* 0.7\n- ancien\n'
        self.assertEqual(publication.release_notes('0.8',text),'## Corrections\n- fichier `ZIP`\n')
        self.assertEqual(publication.release_notes(None,text),'- futur\n')
        for invalid in [text, '* 0.9\n', '* 0.9\n- a\n* 0.9\n- b']:
            with self.assertRaises(ValueError): publication.release_notes('0.9',invalid)

    def test_emp_reintes_et_identite(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'CI_COMMIT_SHA':SHA,'CI_COMMIT_TAG':'0.8'}, clear=True):
            root = Path(temp); file = root/'programme.zip';file.write_bytes(b'fictif')
            record = publication.manifest('programme','windows-x64',[file])
            self.assertEqual(publication.verify(record,root,SHA,'0.8','programme','windows-x64'),{'programme.zip'})
            for kwargs in [{'commit':'b'*40},{'tag':'0.9'},{'target':'linux'}]:
                with self.assertRaises(ValueError): publication.verify(record,root,**kwargs)
            file.write_bytes(b'altere')
            with self.assertRaises(ValueError): publication.verify(record,root)
            record['files'][0]['name']='../fichier'
            with self.assertRaises(ValueError): publication.verify(record,root)
