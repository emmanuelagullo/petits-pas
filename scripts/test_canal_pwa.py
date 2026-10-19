"""Le canal Pages refuse tout suffixe, indépendamment des déclencheurs CI."""
import importlib.util
from pathlib import Path
import unittest
import re
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("preparateur_canal", Path(__file__).with_name("preparer-publication-pwa.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class CanalPwaTests(unittest.TestCase):
    def test_preversions_refusees_avant_toute_requete(self):
        for tag in ("0.12.0-rc.1", "0.12-beta", "0.12.0-dev"):
            with self.subTest(tag=tag), patch.object(p, "json_request") as requete:
                with self.assertRaisesRegex(ValueError, "tag stable"):
                    p.select_job("https://fictif.invalid/api", "1", "2", "a"*40, tag, tag)
                requete.assert_not_called()

    def test_ci_construit_les_rc_et_reserve_pages_aux_tags_stables(self):
        root = Path(__file__).resolve().parent.parent
        source = (root / '.gitlab-ci.yml').read_text()
        nom = 'pwa-publication' if 'pwa-publication:' in source else 'publier-pwa'
        workflow = source.split('workflow:', 1)[1].split('\ntest:', 1)[0]
        promotion = source.split('\n' + nom + ':', 1)[1].split('\n\n', 1)[0]
        pages = (root / 'pwa/publication/pages.yml').read_text()
        expressions = [re.search(r'\$CI_COMMIT_TAG =~ /(.*)/', workflow).group(1),
                       re.search(r'\$CI_COMMIT_TAG =~ /(.*)/', promotion).group(1),
                       re.search(r'\$PWA_SOURCE_TAG =~ /(.*)/', pages).group(1)]
        self.assertTrue(re.fullmatch(expressions[0], '0.12.0-rc.1'))
        for expression in expressions[1:]:
            self.assertTrue(re.fullmatch(expression, '0.12.0'))
            self.assertTrue(re.fullmatch(expression, '0.12'))
            self.assertFalse(re.fullmatch(expression, '0.12.0-rc.1'))
