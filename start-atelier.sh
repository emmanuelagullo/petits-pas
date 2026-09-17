#!/usr/bin/env bash
# Démarrage de l'atelier pédagogique persistant à données exclusivement
# factices. L'initialisation fonctionnelle reste une opération séparée : un
# redéploiement ne recrée et ne modifie jamais les données de l'atelier.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire pour le profil atelier}"
: "${CARNET_S3_BUCKET:?CARNET_S3_BUCKET est obligatoire pour le profil atelier}"
: "${CARNET_VERSION:?CARNET_VERSION est obligatoire pour le profil atelier}"

if [[ "${CARNET_ENVIRONNEMENT_ATELIER:-}" != "oui" ]]; then
    echo "Refus : définir CARNET_ENVIRONNEMENT_ATELIER=oui." >&2
    exit 1
fi

if [[ "${CARNET_ENVIRONNEMENT_EPHEMERE:-}" == "oui" ]]; then
    echo "Refus : un atelier persistant ne peut pas être éphémère." >&2
    exit 1
fi

python3 manage.py diagnostiquer_deploiement --exiger-atelier
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput
python3 manage.py verifier_stockage_objet

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
