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
liste=$(pdfimages -list "$pdf")
printf '%s\n' "$liste"

haute_resolution=$(printf '%s\n' "$liste" | awk '
  NR > 2 && (($13 + 0) > 300 || ($14 + 0) > 300) { n++ }
  END { print n + 0 }
')
if [[ "$haute_resolution" -gt 0 ]]; then
    echo "Avertissement : $haute_resolution image(s) dépassent 300 ppp dans le PDF." >&2
fi
