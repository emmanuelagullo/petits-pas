#!/usr/bin/env bash
# Commande de démarrage pour un environnement persistant.
#
# Les migrations font évoluer la base existante et collectstatic prépare les
# ressources de l'interface. Aucune donnée métier n'est créée, modifiée ou
# supprimée ici : l'initialisation d'une école reste une opération explicite.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire pour le profil persistant}"
: "${CARNET_S3_BUCKET:?CARNET_S3_BUCKET est obligatoire pour le profil persistant}"

python3 manage.py diagnostiquer_deploiement --exiger-persistant
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput
python3 manage.py verifier_stockage_objet

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
