#!/usr/bin/env bash
# Construit et vérifie un paquet coordonné PostgreSQL + médias.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire}"
: "${CARNET_BACKUP_DIR:?CARNET_BACKUP_DIR est obligatoire}"

if [[ $# -ne 1 || ( "$1" != "online" && "$1" != "writes-suspended" ) ]]; then
    echo "Usage : $0 online|writes-suspended" >&2
    exit 1
fi
mode="$1"

if [[ "${CARNET_BACKUP_DIR}" != /* ]]; then
    echo "Refus : CARNET_BACKUP_DIR doit être un chemin absolu." >&2
    exit 1
fi
if [[ "${mode}" == "writes-suspended" \
      && "${CARNET_ECRITURES_SUSPENDUES:-}" != "oui" ]]; then
    echo "Refus : définissez CARNET_ECRITURES_SUSPENDUES=oui." >&2
    exit 1
fi

for commande in date mktemp mv python3; do
    if ! command -v "${commande}" >/dev/null 2>&1; then
        echo "Commande introuvable : ${commande}" >&2
        exit 1
    fi
done

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJET_DIR}"
umask 077
mkdir -p -- "${CARNET_BACKUP_DIR}"

horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
final="${CARNET_BACKUP_DIR}/petits-pas-reprise-${horodatage}"
if [[ -e "${final}" ]]; then
    echo "Refus : le paquet existe déjà : ${final}" >&2
    exit 1
fi

temporaire="$(mktemp -d \
    --tmpdir="${CARNET_BACKUP_DIR}" \
    ".petits-pas-reprise-${horodatage}.incomplete-XXXXXX")"
nettoyer() {
    rm -rf -- "${temporaire}"
}
trap nettoyer EXIT HUP INT TERM

iso_maintenant() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

debut="$(iso_maintenant)"
mkdir -p -- "${temporaire}/postgresql" "${temporaire}/medias"

CARNET_BACKUP_DIR="${temporaire}/postgresql" \
    scripts/sauvegarder-postgresql.sh
fin_base="$(iso_maintenant)"

CARNET_BACKUP_DIR="${temporaire}/medias" \
    scripts/sauvegarder-medias.sh
fin_medias="$(iso_maintenant)"
fin="$(iso_maintenant)"

python3 manage.py creer_manifeste_reprise \
    "${temporaire}" \
    --mode "${mode}" \
    --started-at "${debut}" \
    --database-completed-at "${fin_base}" \
    --media-completed-at "${fin_medias}" \
    --completed-at "${fin}"
python3 manage.py verifier_reprise "${temporaire}"

mv -- "${temporaire}" "${final}"
trap - EXIT HUP INT TERM

echo "Paquet de reprise créé et vérifié : ${final}"
echo "Mode de cohérence                 : ${mode}"
