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

configuration_demo="site/data/demonstration.yaml"
if [[ ! -r "$configuration_demo" ]]; then
    echo "Refus : configuration de démonstration absente : $configuration_demo" >&2
    exit 1
fi

mapfile -t parametres_demo < <(
    python3 - "$configuration_demo" <<'PY'
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as fichier:
    configuration = yaml.safe_load(fichier)

valeurs = (
    configuration["ecole"],
    configuration["identifiants"]["enseignant"],
    configuration["identifiants"]["direction"],
)
for valeur in valeurs:
    if not isinstance(valeur, str) or not valeur or "\n" in valeur:
        raise SystemExit("Configuration de démonstration invalide.")
    print(valeur)
PY
)

if [[ "${#parametres_demo[@]}" -ne 3 ]]; then
    echo "Refus : configuration de démonstration incomplète." >&2
    exit 1
fi

export CARNET_ENVIRONNEMENT_EPHEMERE=oui

python3 manage.py migrate --noinput

python3 manage.py creer_ecole "${parametres_demo[0]}" \
  --commune "Bordeaux" \
  --mdp-enseignant "${parametres_demo[1]}" \
  --mdp-direction "${parametres_demo[2]}"

python3 manage.py charger_referentiel referentiel/trame-cycle1.yaml
python3 manage.py jeu_demo_large

python3 manage.py collectstatic --noinput

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
