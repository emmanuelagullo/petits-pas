"""Le miroir refuse une version non qualifiée et une archive hors périmètre."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import source_inria as source

SHA = "a" * 40


class SourceInriaTests(unittest.TestCase):
    def responses(self):
        return [
            {"id": 12, "path_with_namespace": source.PROJECT},
            {"commit": {"id": SHA}}, {"sha": SHA}, [{"id": 56}],
            {"id": 56, "sha": SHA, "ref": "0.12.0", "status": "success", "source": "push"},
        ]

    def test_selection_tag_commit_pipeline_reussi(self):
        with patch.object(source, "json_request", side_effect=self.responses()) as request:
            selected = source.selectionner_source("0.12.0", SHA)
        self.assertEqual(selected["pipeline_id"], "56")
        query = request.call_args_list[3].args[0]
        self.assertIn("ref=0.12.0", query)
        self.assertIn("sha=" + SHA, query)
        self.assertIn("status=success", query)
        self.assertIn("sort=desc", query)

    def test_main_preversion_et_commit_invalide_sans_reseau(self):
        with patch.object(source, "json_request") as request:
            for tag, commit in [(None, SHA), ("main", SHA), ("0.12.0-rc.1", SHA), ("0.12", "invalide")]:
                with self.subTest(tag=tag), self.assertRaises(ValueError):
                    source.selectionner_source(tag, commit)
            request.assert_not_called()

    def test_tag_deplace_sur_inria_ou_github_refuse(self):
        for index, value in [(1, {"commit": {"id": "b" * 40}}), (2, {"sha": "b" * 40})]:
            responses = self.responses(); responses[index] = value
            with patch.object(source, "json_request", side_effect=responses), self.assertRaisesRegex(ValueError, "même commit"):
                source.selectionner_source("0.12.0", SHA)

    def test_pipeline_absent_en_echec_autre_ref_sha_ou_source_refuse(self):
        responses = self.responses(); responses[3] = []
        with patch.object(source, "json_request", side_effect=responses), self.assertRaisesRegex(ValueError, "Aucun pipeline"):
            source.selectionner_source("0.12.0", SHA)
        for key, value in [("status", "failed"), ("ref", "main"), ("sha", "b" * 40), ("source", "merge_request_event")]:
            responses = self.responses(); responses[4][key] = value
            with self.subTest(key=key), patch.object(source, "json_request", side_effect=responses), self.assertRaises(ValueError):
                source.selectionner_source("0.12.0", SHA)

    def test_job_exact_reussi_uniquement(self):
        selected = {"api": source.API, "project_id": "12", "pipeline_id": "56", "commit": SHA}
        job = {"name": "captures-demonstration", "id": 34, "status": "success", "commit": {"id": SHA}, "pipeline": {"id": 56}}
        with patch.object(source, "json_request", return_value=[job]):
            self.assertTrue(source.trouver_job(selected, job["name"])[1].endswith("/jobs/34/artifacts"))
        for jobs in ([], [job, job], [{**job, "status": "failed"}], [{**job, "commit": {"id": "b" * 40}}], [{**job, "pipeline": {"id": 99}}]):
            with patch.object(source, "json_request", return_value=jobs), self.assertRaises(ValueError):
                source.trouver_job(selected, job["name"])

    def test_import_site_limite_aux_captures_et_essais(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); archive = root / "site.zip"
            with ZipFile(archive, "w") as zipped:
                zipped.writestr("site/static/captures/accueil.webp", b"image fictive")
                zipped.writestr("site/static/essais/ecole-fictive.zip", b"ecole fictive")
                zipped.writestr(".ci-captures-demonstration.log", "journal exclu")
            destination = root / "output"
            source.extraire_site(archive, destination)
            self.assertEqual(len(list(destination.rglob("*.*"))), 2)
            self.assertFalse((destination / ".ci-captures-demonstration.log").exists())

    def test_traversee_lien_collision_et_artefact_incomplet_refuses(self):
        for name in ("../hors-site", "/absolu", "site/static/captures/../hors-site", "site\\capture"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "site.zip"
                with ZipFile(archive, "w") as zipped:
                    zipped.writestr(name, "fictif")
                with self.assertRaises(ValueError):
                    source.extraire_site(archive, Path(temporary) / "output")
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "site.zip"
            link = ZipInfo("site/static/captures/lien"); link.external_attr = 0o120777 << 16
            with ZipFile(archive, "w") as zipped:
                zipped.writestr(link, "cible")
            with self.assertRaisesRegex(ValueError, "lien"):
                source.extraire_site(archive, Path(temporary) / "output")
            with ZipFile(archive, "w") as zipped:
                zipped.writestr("site/static/captures/image", "a")
                zipped.writestr("site/static/captures/./image", "b")
            with self.assertRaisesRegex(ValueError, "répété"):
                source.extraire_site(archive, Path(temporary) / "output")
            with ZipFile(archive, "w") as zipped:
                zipped.writestr("journal.txt", "fictif")
            with self.assertRaisesRegex(ValueError, "absentes"):
                source.extraire_site(archive, Path(temporary) / "output")


if __name__ == "__main__":
    unittest.main()
