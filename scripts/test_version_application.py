"""Version commune : un tag doit désigner le commit exact exécuté."""

import os
import unittest
from unittest.mock import patch

from carnet import version


SHA = "a" * 40
AUTRE_SHA = "b" * 40


class VersionApplicationTests(unittest.TestCase):
    def test_tag_exact_et_developpement(self):
        self.assertEqual(version.version_pour_commit(SHA, {"0.8": SHA}), "0.8")
        self.assertEqual(version.version_pour_commit(SHA, {"0.7": AUTRE_SHA}), "dev.aaaaaaaa")

    def test_tag_annote_utilise_le_commit_cible(self):
        sortie = f"{AUTRE_SHA}\trefs/tags/0.8\n{SHA}\trefs/tags/0.8^{{}}\n"
        with patch.object(version, "git", return_value=sortie):
            self.assertEqual(version.tags_distants(), {"0.8": SHA})

    def test_render_consulte_les_tags_du_depot(self):
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": SHA}, clear=True), patch.object(
            version, "tags_distants", return_value={"0.8": SHA}
        ):
            self.assertEqual(version.version_application(), "0.8")

    def test_construction_sur_branche_ne_devient_pas_release(self):
        with patch.dict(os.environ, {"GITHUB_SHA": SHA, "GITHUB_REF_TYPE": "branch"}, clear=True):
            self.assertEqual(version.version_application(), "dev.aaaaaaaa")


if __name__ == "__main__":
    unittest.main()
