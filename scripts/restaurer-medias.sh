#!/usr/bin/env bash
# Restaure une sauvegarde vérifiée sans écraser les médias déjà présents.
set -euo pipefail

: "${CARNET_AUTORISER_RESTAURATION_MEDIAS:?Définissez CARNET_AUTORISER_RESTAURATION_MEDIAS=oui}"

if [[ "${CARNET_AUTORISER_RESTAURATION_MEDIAS}" != "oui" ]]; then
    echo "Refus : CARNET_AUTORISER_RESTAURATION_MEDIAS doit valoir exactement 'oui'." >&2
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Usage : $0 /chemin/vers/petits-pas-medias-YYYYMMDDTHHMMSSZ" >&2
    exit 1
fi

sauvegarde="$1"
if [[ "${sauvegarde}" != /* || ! -d "${sauvegarde}" ]]; then
    echo "Sauvegarde absolue introuvable : ${sauvegarde}" >&2
    exit 1
fi

python3 manage.py verifier_sauvegarde_medias "${sauvegarde}"
python3 manage.py restaurer_medias "${sauvegarde}"
