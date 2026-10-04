"""Le ZIP public reste traçable dans une image CI sans exécutable Git."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("construction_fictive", Path(__file__).with_name("construire-ecole-fictive.py"))
construction = importlib.util.module_from_spec(spec); spec.loader.exec_module(construction)


class CommitSourcesTests(unittest.TestCase):
    @patch.dict("os.environ", {"CI_COMMIT_SHA": "a" * 40, "GITHUB_SHA": "b" * 40}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError("git"))
    def test_gitlab_sans_git(self, commande):
        self.assertEqual(construction.commit_sources(), "a" * 40)
        commande.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_SHA": "B" * 40}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError("git"))
    def test_github_sans_git(self, commande):
        self.assertEqual(construction.commit_sources(), "b" * 40)
        commande.assert_not_called()

    @patch.dict("os.environ", {"CI_COMMIT_SHA": "invalide"}, clear=True)
    @patch("carnet.version.git", return_value="c" * 40)
    def test_repli_sur_git_local(self, commande):
        self.assertEqual(construction.commit_sources(), "c" * 40)
        commande.assert_called_once_with("rev-parse", "HEAD")

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError("git"))
    def test_sans_git_ni_ci_commit_inconnu(self, _commande):
        self.assertIsNone(construction.commit_sources())
