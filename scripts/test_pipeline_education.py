"""L'attente Inria reste manuelle ; les vraies erreurs ne sont pas masquées."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import source_inria as source

spec = importlib.util.spec_from_file_location('pipeline_education', Path(__file__).with_name('preparer-pipeline-education.py'))
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
SHA = 'a' * 40


class DisponibiliteTests(unittest.TestCase):
    def responses(self, status=None):
        candidates = [] if status is None else [{'id': 56, 'sha': SHA, 'ref': 'main', 'status': status}]
        return [{'id': 12, 'path_with_namespace': source.PROJECT}, {'sha': SHA}, [], candidates]

    def test_absence_et_validation_en_cours_sont_des_attentes(self):
        for status in (None, 'created', 'pending', 'running', 'preparing', 'waiting_for_resource', 'scheduled', 'manual'):
            with self.subTest(status=status), patch.object(source, 'json_request', side_effect=self.responses(status)), self.assertRaises(source.SourceEnAttente):
                source.selectionner_source(None, SHA, distinguer_attente=True)

    def test_pipeline_en_echec_ou_annule_reste_une_erreur(self):
        for status in ('failed', 'canceled', 'skipped'):
            with self.subTest(status=status), patch.object(source, 'json_request', side_effect=self.responses(status)):
                try:
                    source.selectionner_source(None, SHA, distinguer_attente=True)
                except source.SourceEnAttente:
                    self.fail('Un échec Inria a été transformé en attente.')
                except ValueError as error:
                    self.assertIn(status, str(error))
                else:
                    self.fail('Un échec Inria a été accepté.')

    def test_mauvaise_reference_ne_devient_pas_une_attente(self):
        responses = self.responses('running'); responses[-1][0]['sha'] = 'b' * 40
        with patch.object(source, 'json_request', side_effect=responses), self.assertRaisesRegex(ValueError, 'inattendu'):
            source.selectionner_source(None, SHA, distinguer_attente=True)

    def test_commit_absent_sur_github_attend_mais_pas_les_erreurs_reseau(self):
        for code in (404, 403, 500):
            responses = [{'id': 12, 'path_with_namespace': source.PROJECT}, HTTPError('https://fictif', code, 'fictif', {}, None)]
            expected = source.SourceEnAttente if code == 404 else HTTPError
            with self.subTest(code=code), patch.object(source, 'json_request', side_effect=responses), self.assertRaises(expected):
                source.selectionner_source(None, SHA, distinguer_attente=True)

    def test_tag_absent_sur_inria_attend(self):
        responses = [{'id': 12, 'path_with_namespace': source.PROJECT}, HTTPError('https://fictif', 404, 'fictif', {}, None)]
        with patch.object(source, 'json_request', side_effect=responses), self.assertRaises(source.SourceEnAttente):
            source.selectionner_source('0.12.0', SHA, distinguer_attente=True)

    def test_succes_qualifie_garde_la_selection_exacte(self):
        responses = [{'id': 12, 'path_with_namespace': source.PROJECT}, {'sha': SHA}, [{'id': 56}],
                     {'id': 56, 'sha': SHA, 'ref': 'main', 'status': 'success', 'source': 'push'}]
        with patch.object(source, 'json_request', side_effect=responses):
            self.assertEqual(source.selectionner_source(None, SHA, distinguer_attente=True)['pipeline_id'], '56')


class GenerationTests(unittest.TestCase):
    def exercer(self, result):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'enfant.yml'
            env = {'CI_COMMIT_SHA': SHA, 'CI_COMMIT_REF_NAME': 'correction/pages'}
            options = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
            with patch.dict(os.environ, env, clear=True), patch.object(pipeline, 'selectionner_source', **options) as selection:
                pipeline.preparer(destination)
                selection.assert_called_once_with(None, SHA, 'correction/pages', distinguer_attente=True)
            return json.loads(destination.read_text())

    def test_pret_publication_automatique(self):
        config = self.exercer({'pipeline_id': '56'})
        self.assertEqual(config, {'include': [{'local': '/.gitlab/ci/publication-education-taches.yml'}]})

    def test_attente_source_manuelle_bloquante(self):
        config = self.exercer(source.SourceEnAttente('Inria encore en cours'))
        self.assertEqual(config['source-inria']['when'], 'manual')
        self.assertFalse(config['source-inria']['allow_failure'])
        self.assertIn('même commit', config['source-inria']['manual_confirmation'])

    def test_erreurs_fatales_ne_generent_aucune_publication(self):
        for error in (ValueError('commit différent'), URLError('réseau indisponible')):
            with tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'enfant.yml'
                with patch.object(pipeline, 'selectionner_source', side_effect=error), self.assertRaises(type(error)):
                    pipeline.preparer(destination)
                self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
