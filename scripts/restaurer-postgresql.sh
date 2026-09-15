#!/usr/bin/env bash
# Restaure une archive dans une base temporaire explicitement distincte de la
# base active. Le contenu existant de la base cible est supprimé.
set -euo pipefail

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL est obligatoire}"
: "${CARNET_AUTORISER_RESTAURATION:?Définissez CARNET_AUTORISER_RESTAURATION=oui}"

if [[ "${CARNET_AUTORISER_RESTAURATION}" != "oui" ]]; then
    echo "Refus : CARNET_AUTORISER_RESTAURATION doit valoir exactement 'oui'." >&2
    exit 1
fi

if [[ -n "${DATABASE_URL:-}" && "${RESTORE_DATABASE_URL}" == "${DATABASE_URL}" ]]; then
    echo "Refus : la base de restauration est la base active." >&2
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Usage : $0 /chemin/vers/petits-pas-YYYYMMDDTHHMMSSZ.dump" >&2
    exit 1
fi

sauvegarde="$1"
if [[ ! -f "${sauvegarde}" ]]; then
    echo "Sauvegarde introuvable : ${sauvegarde}" >&2
    exit 1
fi

for commande in pg_restore psql sha256sum; do
    if ! command -v "${commande}" >/dev/null 2>&1; then
        echo "Commande introuvable : ${commande}" >&2
        exit 1
    fi
done

if [[ -f "${sauvegarde}.sha256" ]]; then
    repertoire="$(dirname -- "${sauvegarde}")"
    nom="$(basename -- "${sauvegarde}")"
    (
        cd -- "${repertoire}"
        sha256sum --check -- "${nom}.sha256"
    )
else
    echo "Attention : aucune somme SHA-256 associée à la sauvegarde." >&2
fi

echo "Restauration dans la base temporaire configurée..."
pg_restore \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    --file=- \
    "${sauvegarde}" \
    | PGDATABASE="${RESTORE_DATABASE_URL}" psql --set=ON_ERROR_STOP=1

echo "Restauration terminée. Lancez maintenant verifier-restauration.sh."
