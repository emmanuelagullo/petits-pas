#!/usr/bin/env bash
# Commande de démarrage pour la démonstration Render gratuite.
#
# Ce profil suppose un système de fichiers éphémère : Render fournit une
# nouvelle base SQLite vide après une mise en veille, un redémarrage ou un
# redéploiement. Ne jamais l'utiliser avec les ressources persistantes du
# pilote.
set -euo pipefail

if [[ -n "${DATABASE_URL:-}" || -n "${CARNET_S3_BUCKET:-}" ]]; then
    echo "Refus : le profil jetable ne doit utiliser ni PostgreSQL ni S3." >&2
    exit 1
fi

if [[ "${CARNET_ENVIRONNEMENT_ATELIER:-}" == "oui" ]]; then
    echo "Refus : la démonstration éphémère ne peut pas être un atelier." >&2
    exit 1
fi

export CARNET_ENVIRONNEMENT_EPHEMERE=oui
python3 manage.py migrate --noinput
python3 manage.py preparer_demonstration

python3 manage.py collectstatic --noinput

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
