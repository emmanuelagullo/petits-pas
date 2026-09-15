#!/usr/bin/env bash
set -euo pipefail

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGDATA="$PROJET_DIR/.local-persistent/postgresql"

if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    echo "Aucune instance PostgreSQL locale n'a été initialisée."
elif pg_ctl --pgdata="$PGDATA" status >/dev/null 2>&1; then
    pg_ctl --pgdata="$PGDATA" --wait --mode=fast stop
else
    echo "PostgreSQL local est déjà arrêté."
fi
