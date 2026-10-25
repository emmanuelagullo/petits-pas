"""Promotion avec un artefact macOS optionnel : absent, il est ignoré ; présent, il est vérifié."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).with_name("publier-paquets.py"))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
SHA = "a" * 40
TAG = "0.8"
NOTES = "École fictive\nDeuxième ligne.\n".encode("utf-8")


class PublicationMacosTests(unittest.TestCase):
    def execution(self):
        return {"head_repository": {"full_name": publisher.DEPOT}, "conclusion": "success", "status": "completed",
                "path": publisher.WORKFLOW, "head_branch": TAG, "head_sha": SHA, "event": "push", "run_attempt": 1}

    def artefact(self, racine, nom, travail, cible, fichiers, *, contenus=None, notes=NOTES):
        """Zip d'un artefact : fichiers fictifs, manifeste du job donné, notes données."""
        from publication import manifest
        source = racine / ("source-" + nom)
        source.mkdir()
        for fichier in fichiers:
            (source / fichier).write_bytes(notes if fichier == "notes-version.md" else b"fictif " + fichier.encode())
        environnement = {"GITHUB_SHA": SHA, "GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": TAG, "GITHUB_RUN_ID": "123",
                         "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": travail}
        with patch.dict(os.environ, environnement, clear=True):
            enregistrement = manifest("programme", cible, [source / f for f in fichiers])
        manifeste = "publication-" + nom.split("-")[-1] + ".json"
        sortie = io.BytesIO()
        with ZipFile(sortie, "w") as z:
            for fichier in fichiers:
                z.writestr(fichier, (contenus or {}).get(fichier, (source / fichier).read_bytes()))
            z.writestr(manifeste, json.dumps(enregistrement))
        return sortie.getvalue()

    def construire(self, racine, *, macos=True, travail_macos="macos", notes_macos=NOTES, dmg_altere=False,
                   etat_macos=None):
        setup = f"PetitsPas-Setup-{TAG}-x64.exe"
        blobs = {
            1: self.artefact(racine, "linux-linux", "linux", "linux-ubuntu24.04-x86_64",
                             ["PetitsPas-linux.tar.gz", "notes-version.md"]),
            2: self.artefact(racine, "windows-windows", "windows", "windows-x64",
                             ["PetitsPas-windows.zip", setup, "notes-version.md"]),
        }
        setup_zip = io.BytesIO()
        with ZipFile(setup_zip, "w") as z:
            z.writestr(setup, b"fictif " + setup.encode())
        blobs[3] = setup_zip.getvalue()
        artefacts = [{"id": 1, "name": "PetitsPas-linux", "expired": False},
                     {"id": 2, "name": "PetitsPas-windows", "expired": False},
                     {"id": 3, "name": "PetitsPas-Setup-windows", "expired": False}]
        if macos:
            blobs[4] = self.artefact(racine, "macos-macos", travail_macos, "macos-arm64",
                ["PetitsPas-macos-arm64.dmg", "notes-version.md"], notes=notes_macos,
                contenus={"PetitsPas-macos-arm64.dmg": b"altere"} if dmg_altere else None)
            artefacts.append({"id": 4, "name": "PetitsPas-macos", "expired": etat_macos == "expire"})
            if etat_macos == "double":
                artefacts.append({"id": 4, "name": "PetitsPas-macos", "expired": False})
        return artefacts, blobs

    def preparer(self, racine, artefacts, blobs):
        telecharges = []

        def gh(*args, **kwargs):
            identifiant = int(args[1].split("/artifacts/")[1].split("/")[0])
            telecharges.append(identifiant)
            kwargs["stdout"].write(blobs[identifiant])

        destination = racine / "destination"
        destination.mkdir()
        with patch.object(publisher, "verify_tags"), patch.object(
            publisher, "api", side_effect=[self.execution(), {"artifacts": artefacts}, self.execution()]
        ), patch.object(publisher, "gh", side_effect=gh):
            fichiers, commit = publisher.prepare("123", TAG, destination)
        return fichiers, telecharges, destination

    def test_sans_artefact_macos_la_release_reste_celle_de_windows_et_linux(self):
        with tempfile.TemporaryDirectory() as temp:
            racine = Path(temp)
            fichiers, telecharges, _ = self.preparer(racine, *self.construire(racine, macos=False))
            noms = {f.name for f in fichiers}
            self.assertEqual(telecharges, [1, 2, 3])
            self.assertNotIn("PetitsPas-macos-arm64.dmg", noms)
            self.assertNotIn("publication-macos.json", noms)
            self.assertIn("publication-linux.json", noms)
            self.assertEqual(publisher.systemes_publies(fichiers), "Windows x64 et Ubuntu 24.04 x86-64")

    def test_artefact_macos_verifie_publie_le_dmg_son_manifeste_et_son_empreinte(self):
        with tempfile.TemporaryDirectory() as temp:
            racine = Path(temp)
            fichiers, telecharges, destination = self.preparer(racine, *self.construire(racine))
            noms = {f.name for f in fichiers}
            self.assertEqual(telecharges, [1, 2, 3, 4])
            self.assertTrue({"PetitsPas-macos-arm64.dmg", "publication-macos.json", "SHA256SUMS"} <= noms)
            from publication import sha256
            self.assertIn(sha256(destination / "PetitsPas-macos-arm64.dmg"),
                          (destination / "SHA256SUMS").read_text(encoding="utf-8"))
            self.assertIn("Mac à puce Apple", publisher.systemes_publies(fichiers))
            self.assertIn("macOS 15", publisher.systemes_publies(fichiers))

    def test_artefact_macos_present_mais_invalide_bloque_la_publication(self):
        cas = {
            "manifeste d'un autre job": dict(travail_macos="windows"),
            "dmg différent du manifeste": dict(dmg_altere=True),
            "notes divergentes": dict(notes_macos=NOTES + b"Ajout divergent.\n"),
            "artefact expiré": dict(etat_macos="expire"),
            "artefact ambigu": dict(etat_macos="double"),
        }
        for libelle, options in cas.items():
            with self.subTest(libelle), tempfile.TemporaryDirectory() as temp:
                racine = Path(temp)
                with self.assertRaises(ValueError):
                    self.preparer(racine, *self.construire(racine, **options))

    def test_fins_de_ligne_windows_des_notes_macos_acceptees(self):
        with tempfile.TemporaryDirectory() as temp:
            racine = Path(temp)
            fichiers, _, _ = self.preparer(racine, *self.construire(racine, notes_macos=NOTES.replace(b"\n", b"\r\n")))
            self.assertIn("PetitsPas-macos-arm64.dmg", {f.name for f in fichiers})
