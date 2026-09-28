#!/usr/bin/env bash
# Préparer une application WSGI avec PostgreSQL et médias locaux persistants.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire}"
: "${CARNET_MEDIA_ROOT:?CARNET_MEDIA_ROOT est obligatoire}"

python manage.py diagnostiquer_deploiement --exiger-persistant-local
python manage.py verifier_stockage_local
python manage.py migrate --noinput
python manage.py collectstatic --noinput
