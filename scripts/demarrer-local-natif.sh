#!/usr/bin/env bash
set -euo pipefail

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DONNEES_DIR="$PROJET_DIR/.local-persistent"
PGDATA="$DONNEES_DIR/postgresql"
PGSOCKET="$DONNEES_DIR/run"
PGLOG="$DONNEES_DIR/logs/postgresql.log"

command -v initdb >/dev/null || {
    echo "PostgreSQL est absent. Ajoutez postgresql à .envrc puis rechargez direnv." >&2
    exit 1
}

mkdir -p "$DONNEES_DIR/media" "$DONNEES_DIR/logs" "$PGSOCKET"

if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    echo "Initialisation de PostgreSQL dans $PGDATA"
    initdb \
        --pgdata="$PGDATA" \
        --username=petits_pas \
        --auth-local=trust \
        --auth-host=trust
fi

if ! pg_ctl --pgdata="$PGDATA" status >/dev/null 2>&1; then
    pg_ctl \
        --pgdata="$PGDATA" \
        --log="$PGLOG" \
	--options="-h 127.0.0.1 -p 55432 -k $PGSOCKET" \
        --wait start
fi

if ! psql -h 127.0.0.1 -p 55432 -U petits_pas -d postgres -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = 'petits_pas'" | grep -qx 1; then
    createdb -h 127.0.0.1 -p 55432 -U petits_pas petits_pas
fi

# shellcheck source=activer-local-natif.sh
source "$PROJET_DIR/scripts/activer-local-natif.sh"

cd "$PROJET_DIR"
python3 manage.py migrate --noinput
python3 manage.py verifier_stockage_objet

echo
echo "Environnement natif persistant prêt."
echo "Lancez : source scripts/activer-local-natif.sh"
echo "          python3 manage.py runserver"
