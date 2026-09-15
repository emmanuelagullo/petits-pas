#!/usr/bin/env bash
# Exporte les médias du stockage Django vers un répertoire durable vérifiable.
set -euo pipefail

: "${CARNET_BACKUP_DIR:?CARNET_BACKUP_DIR est obligatoire}"

if [[ "${CARNET_BACKUP_DIR}" != /* ]]; then
    echo "Refus : CARNET_BACKUP_DIR doit être un chemin absolu." >&2
    exit 1
fi

umask 077
mkdir -p -- "${CARNET_BACKUP_DIR}"

horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
sauvegarde="${CARNET_BACKUP_DIR}/petits-pas-medias-${horodatage}"

python3 manage.py sauvegarder_medias "${sauvegarde}"
python3 manage.py verifier_sauvegarde_medias "${sauvegarde}"

echo "Sauvegarde des médias créée et vérifiée : ${sauvegarde}"
