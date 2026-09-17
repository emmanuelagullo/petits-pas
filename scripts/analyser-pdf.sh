#!/usr/bin/env bash
# Résumé reproductible d'un carnet PDF sans en extraire les données métier.
set -euo pipefail

pdf=${1:?Usage : scripts/analyser-pdf.sh CARNET.pdf}

if [[ ! -f "$pdf" ]]; then
    echo "Fichier PDF introuvable : $pdf" >&2
    exit 1
fi

echo "Taille : $(wc -c < "$pdf") octets"
pdfinfo "$pdf" | awk '/^(Pages|Page size|File size|PDF version):/'
pdfimages -list "$pdf"
