#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Guix peut fournir PyGObject et WebKit dans le shell actif.
python3 -m venv --system-site-packages .venv-paquet
.venv-paquet/bin/python -m pip install -r requirements-paquet-local.txt
.venv-paquet/bin/python -m PyInstaller --noconfirm --clean scripts/PetitsPas.spec
./dist/PetitsPas/PetitsPas --verifier-distribution
tar -C dist -czf dist/PetitsPas-linux.tar.gz PetitsPas
printf 'Paquet Linux : %s/dist/PetitsPas-linux.tar.gz\n' "$PWD"
printf 'Lancer : %s/dist/PetitsPas/PetitsPas\n' "$PWD"
