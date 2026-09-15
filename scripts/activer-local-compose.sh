#!/usr/bin/env bash
# À sourcer pour utiliser PostgreSQL et MinIO lancés par Compose.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Ce script doit être sourcé : source scripts/activer-local-compose.sh" >&2
    exit 1
fi

unset CARNET_MEDIA_ROOT
export DATABASE_URL="postgresql://petits_pas:petits_pas_local@127.0.0.1:55432/petits_pas"
export CARNET_S3_BUCKET="petits-pas"
export CARNET_S3_ENDPOINT_URL="http://127.0.0.1:59000"
export CARNET_S3_REGION="us-east-1"
export CARNET_S3_ACCESS_KEY="petits_pas"
export CARNET_S3_SECRET_KEY="petits_pas_local"
export CARNET_S3_URL_EXPIRATION="300"
export CARNET_SECRET_KEY="local-compose-development-key-do-not-reuse"
export CARNET_DEBUG="0"
export CARNET_HOSTS="127.0.0.1,localhost"
export CARNET_CSRF_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"
