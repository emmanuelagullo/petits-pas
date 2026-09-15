#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if command -v docker >/dev/null 2>&1; then
    compose=(docker compose)
elif command -v podman >/dev/null 2>&1; then
    compose=(podman compose)
else
    echo "Docker Compose ou Podman Compose est requis." >&2
    exit 1
fi

"${compose[@]}" -f compose.local.yaml up -d

source scripts/activer-local-persistent.sh

python3 manage.py diagnostiquer_deploiement --exiger-persistant
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput
python3 manage.py verifier_stockage_objet

echo
echo "Environnement persistant local prêt."
echo "Application : python3 manage.py runserver"
echo "MinIO       : http://127.0.0.1:59001"
