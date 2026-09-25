"""Vérifie les chemins de publication sans accès aux forges ni publication réelle."""

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("publier-paquets.sh")
SHA = "a" * 40


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        for name in ("python3", "cut", "mktemp", "rm", "realpath", "cp", "cat"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.linux = self.base / "PetitsPas-linux.tar.gz"
        with tarfile.open(self.linux, "w:gz") as archive:
            contenu = b"programme fictif"
            entree = tarfile.TarInfo("PetitsPas/PetitsPas")
            entree.size = len(contenu)
            archive.addfile(entree, io.BytesIO(contenu))
        self.windows = self.base / "PetitsPas-windows.zip"
        with zipfile.ZipFile(self.windows, "w") as archive:
            archive.writestr("PetitsPas/PetitsPas.exe", b"programme fictif")
        self.journal = self.base / "appels"
        self.creer_commande("git", '''#!/bin/sh
if [ "$1" = rev-parse ]; then echo "$FAKE_SHA"; else printf '%s\\t%s\\n' "$FAKE_SHA" "$4"; fi
''')

    def creer_commande(self, nom, code):
        chemin = self.bin / nom
        chemin.write_text(code)
        chemin.chmod(0o755)

    def activer_gh(self):
        self.creer_commande("gh", '''#!/bin/sh
printf 'gh %s\\n' "$*" >> "$FAKE_LOG"
if [ "$1" = run ] && [ "$2" = view ]; then
  printf '{"conclusion":"success","headSha":"%s","workflowName":"Paquets autonomes Linux et Windows (prototype)"}\\n' "$FAKE_SHA"
elif [ "$1" = run ] && [ "$2" = download ]; then
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --name) nom=$2; shift 2 ;;
      --dir) dossier=$2; shift 2 ;;
      *) shift ;;
    esac
  done
  /bin/mkdir -p "$dossier"
  if [ "$nom" = PetitsPas-linux ]; then
    cp "$FAKE_LINUX" "$dossier/"
  else
    cp "$FAKE_WINDOWS" "$dossier/"
  fi
fi
''')

    def activer_glab(self):
        self.creer_commande("glab", '''#!/bin/sh
printf 'glab %s\\n' "$*" >> "$FAKE_LOG"
''')

    def lancer(self, *arguments):
        env = dict(os.environ, PATH=str(self.bin), FAKE_SHA=SHA,
                   FAKE_LOG=str(self.journal), FAKE_LINUX=str(self.linux),
                   FAKE_WINDOWS=str(self.windows))
        return subprocess.run(["/bin/bash", str(SCRIPT), "123", "v1.0-test", *arguments],
                              env=env, text=True, capture_output=True)

    def test_gh_seul_publie_les_archives_et_explique_gitlab(self):
        self.activer_gh()
        resultat = self.lancer()
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        appels = self.journal.read_text()
        self.assertIn("gh release create", appels)
        self.assertIn("gh release edit", appels)
        self.assertIn("/-/releases/new", resultat.stdout)
        self.assertIn("PetitsPas-windows.zip", resultat.stdout)

    def test_glab_seul_publie_avec_archives_et_sha_fournis(self):
        self.activer_glab()
        resultat = self.lancer(str(self.linux), str(self.windows), SHA)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("glab release create", self.journal.read_text())
        self.assertIn("/releases/new", resultat.stdout)

    def test_deux_cli_publient_les_memes_archives_sur_les_deux_forges(self):
        self.activer_gh()
        self.activer_glab()
        resultat = self.lancer()
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        appels = self.journal.read_text().splitlines()
        self.assertLess(
            next(i for i, appel in enumerate(appels) if appel.startswith("gh release create")),
            next(i for i, appel in enumerate(appels) if appel.startswith("glab release create")),
        )
        self.assertTrue(appels[-1].startswith("gh release edit"))

    def test_sha_manuel_incorrect_refuse_la_publication(self):
        self.activer_glab()
        resultat = self.lancer(str(self.linux), str(self.windows), "b" * 40)
        self.assertNotEqual(resultat.returncode, 0)
        self.assertIn("le tag local pointe", resultat.stderr.lower())
        self.assertFalse(self.journal.exists())

    def test_sans_cli_ne_publie_pas(self):
        resultat = self.lancer()
        self.assertNotEqual(resultat.returncode, 0)
        self.assertIn("ni gh ni glab", resultat.stderr)
        self.assertIn("/-/releases/new", resultat.stdout)
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
