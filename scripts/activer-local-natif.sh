#!/usr/bin/env bash
# À sourcer pour utiliser PostgreSQL et les médias persistants locaux.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo \
        "Ce script doit être sourcé : source scripts/activer-local-natif.sh" \
        >&2
    exit 1
fi

CARNET_PROJET_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
        pwd
)"

# Évite qu'un profil S3 précédemment activé reste partiellement configuré.
unset CARNET_S3_BUCKET
unset CARNET_S3_ENDPOINT_URL
unset CARNET_S3_REGION
unset CARNET_S3_ACCESS_KEY
unset CARNET_S3_SECRET_KEY
unset CARNET_S3_URL_EXPIRATION

export DATABASE_URL="postgresql://petits_pas@127.0.0.1:55432/petits_pas"
export CARNET_MEDIA_ROOT="$CARNET_PROJET_DIR/.local-persistent/media"
export CARNET_SECRET_KEY="local-native-development-key-do-not-reuse"
export CARNET_DEBUG="1"
export CARNET_HOSTS="127.0.0.1,localhost"
export CARNET_CSRF_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"

unset CARNET_PROJET_DIR
