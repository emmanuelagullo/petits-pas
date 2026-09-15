#!/usr/bin/env bash
# Produit une sauvegarde PostgreSQL au format personnalisé, accompagnée de sa
# somme SHA-256. Le répertoire cible doit être choisi explicitement : ce script
# ne suppose pas que le disque de l'application est persistant.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire}"
: "${CARNET_BACKUP_DIR:?CARNET_BACKUP_DIR est obligatoire}"

if [[ "${CARNET_BACKUP_DIR}" != /* ]]; then
    echo "Refus : CARNET_BACKUP_DIR doit être un chemin absolu." >&2
    exit 1
fi

for commande in pg_dump pg_restore sha256sum; do
    if ! command -v "${commande}" >/dev/null 2>&1; then
        echo "Commande introuvable : ${commande}" >&2
        exit 1
    fi
done

umask 077
mkdir -p -- "${CARNET_BACKUP_DIR}"

horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
nom="petits-pas-${horodatage}.dump"
sauvegarde="${CARNET_BACKUP_DIR}/${nom}"

if [[ -e "${sauvegarde}" ]]; then
    echo "Refus : la sauvegarde existe déjà : ${sauvegarde}" >&2
    exit 1
fi

pg_dump \
    --dbname="${DATABASE_URL}" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file="${sauvegarde}"

# Vérifie immédiatement que pg_restore sait lire l'archive produite.
pg_restore --list "${sauvegarde}" >/dev/null

(
    cd -- "${CARNET_BACKUP_DIR}"
    sha256sum -- "${nom}" > "${nom}.sha256"
)

echo "Sauvegarde créée : ${sauvegarde}"
echo "Somme SHA-256   : ${sauvegarde}.sha256"
