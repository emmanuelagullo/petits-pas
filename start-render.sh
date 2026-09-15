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

python manage.py migrate --noinput

python manage.py creer_ecole "Ma Belle École" \
  --commune "Bordeaux" \
  --mdp-enseignant "${CARNET_MDP_ENSEIGNANT:-maclasse}" \
  --mdp-direction "${CARNET_MDP_DIRECTION:-pressense}"

python manage.py charger_referentiel referentiel/trame-cycle1.yaml
python manage.py jeu_demo

python manage.py collectstatic --noinput

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
