#!/usr/bin/env bash
# Adapter le chargeur et zlib d'un bootloader PyInstaller construit sous Guix.
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
repare=0
if [[ ! -e "$chargeur" ]]; then
    python_binaire=$(readlink -f "$(command -v python3)")
    chargeur_python=$("${patchelf_cmd[@]}" --print-interpreter "$python_binaire")
    if [[ ! -f "$chargeur_python" ]]; then
        printf 'Chargeur Python indisponible : %s\n' "$chargeur_python" >&2
        exit 1
    fi
    "${patchelf_cmd[@]}" --set-interpreter "$chargeur_python" "$binaire"
    printf 'Chargeur ELF remplacé : %s → %s\n' "$chargeur" "$chargeur_python"
    chargeur=$chargeur_python
    repare=1
fi

# Le chargeur Guix ne cherche pas automatiquement les .so dans _internal.
# N'ajouter zlib que si la résolution des dépendances signale son absence.
dependances=$("$chargeur" --list "$binaire" 2>&1 || true)
if [[ "$dependances" == *libz.so.1* ]] && \
   { [[ "$dependances" == *'not found'* ]] || [[ "$dependances" == *'cannot open'* ]]; }; then
    dossier_lib=$(dirname "$binaire")/_internal
    mkdir -p "$dossier_lib"
    if [[ ! -f "$dossier_lib/libz.so.1" ]]; then
        # Charger zlib depuis Python pour identifier sa bibliothèque Guix
        # effective, sans deviner un chemin dans /gnu/store.
        chemin_zlib=$(python3 - <<'PY'
import ctypes
import os
import zlib  # noqa: F401

try:
    ctypes.CDLL('libz.so.1')
except OSError:
    pass
for ligne in open('/proc/self/maps', encoding='utf-8'):
    chemin = ligne.split()[-1]
    if '/libz.so.' in chemin and os.path.isfile(chemin):
        print(chemin)
        break
PY
        )
        if [[ -z "$chemin_zlib" ]] && command -v guix >/dev/null 2>&1; then
            chemin_zlib=$(guix build zlib)/lib/libz.so.1
        fi
        if [[ ! -f "$chemin_zlib" ]]; then
            printf 'libz.so.1 introuvable dans Python ou le paquet Guix zlib.\n' >&2
            exit 1
        fi
        cp -L -- "$chemin_zlib" "$dossier_lib/libz.so.1"
        printf 'Bibliothèque zlib ajoutée au paquet : %s\n' "$chemin_zlib"
    fi
    rpath=$("${patchelf_cmd[@]}" --print-rpath "$binaire")
    if [[ "$rpath" != *'${ORIGIN}/_internal'* ]]; then
        "${patchelf_cmd[@]}" --set-rpath "${rpath:+$rpath:}\$ORIGIN/_internal" "$binaire"
    fi
    apres=$("$chargeur" --list "$binaire" 2>&1 || true)
    if [[ "$apres" == *'libz.so.1 => not found'* ]]; then
        printf 'libz.so.1 reste introuvable après correction.\n' >&2
        exit 1
    fi
    repare=1
fi
if (( ! repare )); then
    printf 'Chargeur présent et libz.so.1 résolue : autre cause. Dépendances :\n%s\n' "$dependances" >&2
    exit 1
fi
