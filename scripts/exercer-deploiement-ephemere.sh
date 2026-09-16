#!/usr/bin/env bash
# Valide le profil persistant dans des services éphémères déjà démarrés.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL est obligatoire}"
: "${CARNET_S3_BUCKET:?CARNET_S3_BUCKET est obligatoire}"
: "${CARNET_S3_ENDPOINT_URL:?CARNET_S3_ENDPOINT_URL est obligatoire}"

if [[ "${CARNET_ENVIRONNEMENT_EPHEMERE:-}" != "oui" ]]; then
    echo "Refus : définissez CARNET_ENVIRONNEMENT_EPHEMERE=oui." >&2
    exit 1
fi

for commande in curl createdb dropdb pg_dump pg_restore psql python3; do
    if ! command -v "${commande}" >/dev/null 2>&1; then
        echo "Commande introuvable : ${commande}" >&2
        exit 1
    fi
done

PROJET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJET_DIR}"

application_pid=""
journal="${PROJET_DIR}/.ci-deploiement-ephemere.log"

nettoyer() {
    statut=$?
    trap - EXIT HUP INT TERM
    set +e
    if [[ -n "${application_pid}" ]]; then
        kill "${application_pid}" >/dev/null 2>&1
        wait "${application_pid}" >/dev/null 2>&1
    fi
    if [[ ${statut} -ne 0 && -f "${journal}" ]]; then
        echo "Dernières lignes du journal de l’application :" >&2
        tail -n 100 "${journal}" >&2
    fi
    exit "${statut}"
}
trap nettoyer EXIT HUP INT TERM

python3 - <<'PY'
import os
import time

import boto3
import psycopg

for tentative in range(60):
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]):
            break
    except psycopg.OperationalError:
        if tentative == 59:
            raise
        time.sleep(1)

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["CARNET_S3_ENDPOINT_URL"],
    region_name=os.environ.get("CARNET_S3_REGION"),
    aws_access_key_id=os.environ["CARNET_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["CARNET_S3_SECRET_KEY"],
)
bucket = os.environ["CARNET_S3_BUCKET"]

for tentative in range(60):
    try:
        s3.list_buckets()
        break
    except Exception:
        if tentative == 59:
            raise
        time.sleep(1)

existants = {entree["Name"] for entree in s3.list_buckets().get("Buckets", [])}
if bucket not in existants:
    s3.create_bucket(Bucket=bucket)
PY

./start-persistent.sh >"${journal}" 2>&1 &
application_pid=$!

application_prete=0
for _ in $(seq 1 60); do
    if curl --fail --silent --show-error \
        http://127.0.0.1:8000/health/ \
        | grep -q '"status": "ok"'; then
        application_prete=1
        break
    fi
    if ! kill -0 "${application_pid}" 2>/dev/null; then
        break
    fi
    sleep 1
done
if [[ ${application_prete} -ne 1 ]]; then
    echo "L’application n’a pas répondu correctement à /health/." >&2
    exit 1
fi

python3 manage.py shell -c '
from django.core.files.storage import default_storage
from suivi.models import Ecole

if Ecole.objects.exists():
    raise SystemExit("La base éphémère contient déjà une école.")
sous_repertoires, fichiers = default_storage.listdir("")
if sous_repertoires or fichiers:
    raise SystemExit("Le bucket éphémère contient déjà des objets.")
'

python3 manage.py creer_ecole \
    "École éphémère CI" \
    --commune "Intégration continue" \
    --mdp-enseignant "enseignant-ci" \
    --mdp-direction "direction-ci"
python3 manage.py charger_referentiel referentiel/trame-cycle1.yaml
python3 manage.py jeu_demo
python3 manage.py shell -c '
from django.core.files.base import ContentFile
from suivi.models import Observation

observation = Observation.objects.first()
observation.photo.save(
    "preuve-deploiement-ci.txt",
    ContentFile(b"preuve du stockage S3 de Petits Pas\n"),
    save=True,
)
print(f"Média de contrôle créé : {observation.photo.name}")
'

python3 manage.py verifier_stockage_objet
python3 manage.py verifier_reprise_restauree

export CARNET_BACKUP_DIR="${PROJET_DIR}/backups"
scripts/sauvegarder-reprise.sh online

shopt -s nullglob
paquets=("${CARNET_BACKUP_DIR}"/petits-pas-reprise-*)
if [[ ${#paquets[@]} -ne 1 ]]; then
    echo "Un unique paquet de reprise était attendu." >&2
    exit 1
fi
scripts/exercer-reprise-local.sh "${paquets[0]}"

echo "Déploiement éphémère complet validé."
