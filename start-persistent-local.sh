#!/usr/bin/env bash
# Variante avec serveur WSGI Gunicorn ; utiliser le script de préparation seul
# lorsque l'hébergement fournit déjà un serveur WSGI.
set -euo pipefail

"$(dirname "$0")/scripts/preparer-deploiement-persistant-local.sh"
exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
