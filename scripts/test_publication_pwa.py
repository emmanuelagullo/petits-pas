"""Refuser un mauvais pipeline, les bundles de test et les artefacts altérés."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

spec = importlib.util.spec_from_file_location("publication", Path(__file__).with_name("preparer-publication-pwa.py"))
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "bundle"
        self.root.mkdir()
        names = ["index.html", "worker.js", "storage.js", "sw.js", "application.zip"]
        for name in names:
            (self.root / name).write_bytes(b"contenu fictif")
        self.config = {"testMode": False, "version": "pwa-prototype." + "a" * 16,
            "assets": [{"url": "/" + name, "sha256": publication.sha256(self.root / name)} for name in names]}
        self.write_config()

    def write_config(self):
        (self.root / "config.json").write_text(json.dumps(self.config))

    def archive(self):
        archive = Path(self.temp.name) / "artifact.zip"
        with ZipFile(archive, "w") as zipped:
            for file in self.root.iterdir():
                zipped.write(file, "dist/pwa/" + file.name)
            zipped.writestr("resultats-pwa.json", json.dumps([{"test": "parcours fictif réussi"}]))
        return archive

    def test_publication_extracts_only_verified_bundle(self):
        archive = self.archive()
        with ZipFile(archive, "a") as zipped:
            zipped.writestr("notes-non-publiees.txt", "information fictive")
        destination = Path(self.temp.name) / "extracted"
        root, config, report = publication.extract_bundle(archive, destination)
        self.assertEqual(config["version"], self.config["version"])
        self.assertEqual({f.name for f in root.iterdir()}, {f.name for f in self.root.iterdir()})
        self.assertFalse((destination / "notes-non-publiees.txt").exists())
        self.assertEqual(len(report), 64)

    def test_test_bundle_is_refused(self):
        self.config["testMode"] = True
        self.write_config()
        with self.assertRaisesRegex(ValueError, "Bundle de test"):
            publication.validate_bundle(self.root)

    def test_altered_and_missing_files_are_refused(self):
        (self.root / "worker.js").write_text("altération fictive")
        with self.assertRaisesRegex(ValueError, "altéré"):
            publication.validate_bundle(self.root)
        (self.root / "worker.js").unlink()
        with self.assertRaises(FileNotFoundError):
            publication.validate_bundle(self.root)

    def test_unexpected_file_is_not_published(self):
        (self.root / "ecole-fictive.sqlite3").write_bytes(b"fictif")
        with self.assertRaisesRegex(ValueError, "non déclarés"):
            publication.validate_bundle(self.root)

    def test_traversal_and_symlink_in_zip_are_refused(self):
        for name, mode in [("dist/pwa/../../ailleurs", 0), ("dist/pwa/lien", 0o120777 << 16)]:
            with self.subTest(name=name):
                archive = self.archive()
                with ZipFile(archive, "a") as zipped:
                    entry = ZipInfo(name)
                    entry.external_attr = mode
                    zipped.writestr(entry, "fictif")
                with self.assertRaisesRegex(ValueError, "Chemin ou lien"):
                    publication.extract_bundle(archive, Path(self.temp.name) / ("output" + str(mode)))

    def test_pages_url_must_be_https_and_root(self):
        publication.require_root_url("https://pwa-fictive.example/")
        for url in ["http://pwa-fictive.example/", "https://example/petits-pas/", "https://example/?x=1"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                publication.require_root_url(url)

    def test_select_exact_pipeline_and_job_with_pagination(self):
        commit = "b" * 40
        responses = [
            ({"id": 12, "path_with_namespace": publication.SOURCE, "default_branch": "main"}, {}),
            ({"sha": commit, "ref": "main"}, {}),
            ([{"name": "autre-job-fictif"}], {"X-Next-Page": "2"}),
            ([{"id": 34, "name": "pwa-prototype", "status": "success", "commit": {"id": commit}, "pipeline": {"id": 56}}], {}),
        ]
        with patch.object(publication, "json_request", side_effect=responses) as request:
            job, url = publication.select_job("https://forge-fictive.example/api/v4", "12", "56", commit)
        self.assertEqual(job["id"], 34)
        self.assertTrue(url.endswith("/projects/12/jobs/34/artifacts"))
        self.assertIn("/pipelines/56/jobs?", request.call_args_list[2].args[0])
        self.assertTrue(request.call_args_list[3].args[0].endswith("page=2"))

    def test_failed_job_or_wrong_commit_cannot_be_published(self):
        commit = "b" * 40
        for status, sha in [("failed", commit), ("success", "c" * 40)]:
            responses = [
                ({"id": 12, "path_with_namespace": publication.SOURCE, "default_branch": "main"}, {}),
                ({"sha": commit, "ref": "main"}, {}),
                ([{"id": 34, "name": "pwa-prototype", "status": status, "commit": {"id": sha}, "pipeline": {"id": 56}}], {}),
            ]
            with self.subTest(status=status, sha=sha), patch.object(publication, "json_request", side_effect=responses), self.assertRaisesRegex(ValueError, "n'a pas réussi"):
                publication.select_job("https://forge-fictive.example/api/v4", "12", "56", commit)


if __name__ == "__main__":
    unittest.main()
