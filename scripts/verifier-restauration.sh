#!/usr/bin/env bash
# Vérifie les migrations et affiche uniquement des comptages non sensibles de
# la base restaurée. Aucune donnée n'est modifiée.
set -euo pipefail

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL est obligatoire}"

if [[ -n "${DATABASE_URL:-}" && "${RESTORE_DATABASE_URL}" == "${DATABASE_URL}" ]]; then
    echo "Refus : la base de vérification est la base active." >&2
    exit 1
fi

DATABASE_URL="${RESTORE_DATABASE_URL}" python manage.py migrate --check
DATABASE_URL="${RESTORE_DATABASE_URL}" python manage.py shell -c '
from suivi.models import Classe, Competence, Ecole, Eleve, Observation

print("Restauration lisible :")
print(f"- écoles       : {Ecole.objects.count()}")
print(f"- classes      : {Classe.objects.count()}")
print(f"- élèves       : {Eleve.objects.count()}")
print(f"- compétences  : {Competence.objects.count()}")
print(f"- observations : {Observation.objects.count()}")
'

echo "Vérification terminée sans modification de la base."
