#!/usr/bin/env bash
# Construire le programme macOS (Apple Silicon, non signé) : PetitsPas.app dans PetitsPas-macos-arm64.dmg.
# Prérequis : Homebrew et Pango (brew install pango), dont les bibliothèques sont embarquées dans le .app.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    printf 'Ce script construit pour macOS Apple Silicon (arm64) seulement.\n' >&2
    exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
    printf 'Homebrew est requis pour fournir Pango : https://brew.sh\n' >&2
    exit 1
fi
export PETITS_PAS_PANGO_BIN="${PETITS_PAS_PANGO_BIN:-$(brew --prefix)/lib}"
if [ ! -d "$PETITS_PAS_PANGO_BIN" ]; then
    printf 'Dossier des bibliothèques Pango introuvable : %s (brew install pango)\n' "$PETITS_PAS_PANGO_BIN" >&2
    exit 1
fi

python3 -m carnet.version > version-application.txt
venv_construction=$(mktemp -d "${TMPDIR:-/tmp}/petits-pas-construction-XXXXXXXX")
trap 'rm -rf -- "$venv_construction"' EXIT
python3 -m venv "$venv_construction"
"$venv_construction/bin/python" -m pip install -r requirements-paquet-local.txt
"$venv_construction/bin/python" -m unittest discover -s scripts -p test_archive_historique.py
"$venv_construction/bin/python" scripts/construire-ecole-fictive.py
# Construit PetitsPas.app, exige --verifier-distribution du vrai programme, puis crée le DMG.
"$venv_construction/bin/python" -m pas_communs.construire_bureau --spec scripts/PetitsPas.spec --nom PetitsPas
printf 'Paquet macOS : %s/dist/PetitsPas-macos-arm64.dmg\n' "$PWD"
