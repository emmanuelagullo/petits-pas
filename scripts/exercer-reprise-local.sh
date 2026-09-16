#!/usr/bin/env bash
# Restaure un paquet #J9 dans une base et un stockage locaux temporaires.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire}"

if [[ $# -ne 1 ]]; then
    echo "Usage : $0 /chemin/absolu/vers/petits-pas-reprise-..." >&2
    exit 1
fi

paquet="$1"
if [[ "${paquet}" != /* || ! -d "${paquet}" ]]; then
    echo "Paquet de reprise absolu introuvable : ${paquet}" >&2
    exit 1
fi

for commande in createdb date dropdb mktemp python3; do
    if ! command -v "${commande}" >/dev/null 2>&1; then
        echo "Commande introuvable : ${commande}" >&2
        exit 1
    fi
done

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJET_DIR}"

scripts/verifier-reprise.sh "${paquet}"

shopt -s nullglob
dumps=("${paquet}"/postgresql/*.dump)
sauvegardes_medias=("${paquet}"/medias/petits-pas-medias-*)
if [[ ${#dumps[@]} -ne 1 || ${#sauvegardes_medias[@]} -ne 1 ]]; then
    echo "Contenu du paquet inattendu après vérification." >&2
    exit 1
fi

racine_reprise="${CARNET_RECOVERY_DIR:-${PROJET_DIR}/.local-recovery}"
if [[ "${racine_reprise}" != /* ]]; then
    echo "Refus : CARNET_RECOVERY_DIR doit être un chemin absolu." >&2
    exit 1
fi
mkdir -p -- "${racine_reprise}"
medias_restauration="$(mktemp -d \
    --tmpdir="${racine_reprise}" \
    "medias-XXXXXXXX")"

horodatage="$(date -u +%Y%m%dT%H%M%SZ)"
base_restauration="petits_pas_recovery_${horodatage,,}_$$"
base_creee=0

url_restauration="$(python3 - "${DATABASE_URL}" "${base_restauration}" <<'PY'
import sys
from urllib.parse import quote, urlsplit, urlunsplit

source, database = sys.argv[1:]
url = urlsplit(source)
if url.scheme not in {"postgres", "postgresql"} or not url.netloc:
    raise SystemExit("DATABASE_URL doit être une URL PostgreSQL complète.")
print(urlunsplit((url.scheme, url.netloc, "/" + quote(database), url.query, "")))
PY
)"

nettoyer() {
    statut=$?
    trap - EXIT
    set +e
    if [[ "${CARNET_CONSERVER_REPRISE_LOCALE:-}" == "oui" ]]; then
        echo "Cibles de l’exercice conservées :"
        echo "- base PostgreSQL : ${base_restauration}"
        echo "- médias          : ${medias_restauration}"
    else
        statut_nettoyage=0
        if [[ ${base_creee} -eq 1 ]]; then
            dropdb --if-exists \
                --maintenance-db="${DATABASE_URL}" \
                "${base_restauration}" || statut_nettoyage=1
        fi
        rm -rf -- "${medias_restauration}" || statut_nettoyage=1
        if [[ ${statut_nettoyage} -eq 0 ]]; then
            echo "Cibles temporaires de l’exercice supprimées."
        else
            echo "Attention : nettoyage incomplet des cibles temporaires." >&2
            if [[ ${statut} -eq 0 ]]; then
                statut=1
            fi
        fi
    fi
    exit "${statut}"
}
trap nettoyer EXIT

createdb --maintenance-db="${DATABASE_URL}" "${base_restauration}"
base_creee=1

RESTORE_DATABASE_URL="${url_restauration}" \
CARNET_AUTORISER_RESTAURATION=oui \
    scripts/restaurer-postgresql.sh "${dumps[0]}"

(
    unset CARNET_S3_BUCKET CARNET_S3_ENDPOINT_URL CARNET_S3_REGION
    unset CARNET_S3_ACCESS_KEY CARNET_S3_SECRET_KEY CARNET_S3_URL_EXPIRATION
    export CARNET_MEDIA_ROOT="${medias_restauration}"
    export CARNET_AUTORISER_RESTAURATION_MEDIAS=oui
    scripts/restaurer-medias.sh "${sauvegardes_medias[0]}"
)

RESTORE_DATABASE_URL="${url_restauration}" \
    scripts/verifier-restauration.sh

(
    unset CARNET_S3_BUCKET CARNET_S3_ENDPOINT_URL CARNET_S3_REGION
    unset CARNET_S3_ACCESS_KEY CARNET_S3_SECRET_KEY CARNET_S3_URL_EXPIRATION
    export DATABASE_URL="${url_restauration}"
    export CARNET_MEDIA_ROOT="${medias_restauration}"
    python3 manage.py check
    python3 manage.py verifier_reprise_restauree
)

echo "Exercice de reprise locale réussi."
