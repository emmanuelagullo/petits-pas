#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Guix peut fournir PyGObject et WebKit dans le shell actif.
venv_construction=$(mktemp -d "${TMPDIR:-/tmp}/petits-pas-construction-XXXXXXXX")
trap 'rm -rf -- "$venv_construction"' EXIT
python3 -m venv --system-site-packages "$venv_construction"
"$venv_construction/bin/python" -c 'import gi; gi.require_version("WebKit2", "4.1"); from gi.repository import WebKit2' || {
    printf 'WebKit2 4.1 introuvable dans le Python de construction : activez le shell Guix avec webkitgtk-for-gtk3.\n' >&2
    exit 1
}
"$venv_construction/bin/python" -m pip install -r requirements-paquet-local.txt
"$venv_construction/bin/python" -m PyInstaller --noconfirm --clean scripts/PetitsPas.spec
if ! ./dist/PetitsPas/PetitsPas --verifier-distribution; then
    # Le bootloader de la roue PyInstaller peut attendre /lib64/ld-linux,
    # absent d'un système Guix. Lier au chargeur du Python de construction.
    bash scripts/corriger-interpreteur-linux.sh ./dist/PetitsPas/PetitsPas
    ./dist/PetitsPas/PetitsPas --verifier-distribution
fi
tar -C dist -czf dist/PetitsPas-linux.tar.gz PetitsPas
printf 'Paquet Linux : %s/dist/PetitsPas-linux.tar.gz\n' "$PWD"
printf 'Lancer : %s/dist/PetitsPas/PetitsPas\n' "$PWD"
