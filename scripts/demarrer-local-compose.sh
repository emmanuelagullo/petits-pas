#!/usr/bin/env bash
set -euo pipefail

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJET_DIR"

if command -v docker >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v podman >/dev/null 2>&1; then
    COMPOSE=(podman compose)
else
    echo "Docker Compose ou Podman Compose est requis." >&2
    exit 1
fi

"${COMPOSE[@]}" -f compose.local.yaml up -d

# shellcheck source=activer-local-compose.sh
source "$PROJET_DIR/scripts/activer-local-compose.sh"

python3 manage.py diagnostiquer_deploiement --exiger-persistant
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput
python3 manage.py verifier_stockage_objet

echo
echo "Environnement Compose persistant prêt."
echo "Lancez : source scripts/activer-local-compose.sh"
echo "          python3 manage.py runserver"
