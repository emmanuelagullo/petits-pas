#!/usr/bin/env bash
# Adapter un bootloader PyInstaller construit sous Guix si son chargeur ELF
# pointe vers /lib64/... alors que le Python de construction utilise /gnu/store/...
set -euo pipefail
if (( $# != 1 )); then
    printf 'Usage : %s CHEMIN_EXECUTABLE\n' "$0" >&2
    exit 2
fi
binaire=$1
if [[ ! -f "$binaire" ]]; then
    printf 'Binaire absent : %s\n' "$binaire" >&2
    exit 1
fi
if command -v patchelf >/dev/null 2>&1; then
    patchelf_cmd=(patchelf)
elif command -v guix >/dev/null 2>&1; then
    patchelf_cmd=(guix shell patchelf -- patchelf)
else
    printf 'Impossible de diagnostiquer le chargeur ELF : installer patchelf (ou utiliser guix shell patchelf).\n' >&2
    exit 1
fi
chargeur=$("${patchelf_cmd[@]}" --print-interpreter "$binaire")
if [[ -e "$chargeur" ]]; then
    printf 'Chargeur ELF présent : %s. La panne a une autre cause.\n' "$chargeur" >&2
    exit 1
fi
python_binaire=$(readlink -f "$(command -v python3)")
chargeur_python=$("${patchelf_cmd[@]}" --print-interpreter "$python_binaire")
if [[ ! -f "$chargeur_python" ]]; then
    printf 'Chargeur Python indisponible : %s\n' "$chargeur_python" >&2
    exit 1
fi
"${patchelf_cmd[@]}" --set-interpreter "$chargeur_python" "$binaire"
printf 'Chargeur ELF remplacé : %s → %s\n' "$chargeur" "$chargeur_python"
