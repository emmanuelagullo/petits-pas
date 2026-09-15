#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != /* || ! -d "$1" ]]; then
    echo "Usage : $0 /chemin/absolu/vers/petits-pas-reprise-YYYYMMDDTHHMMSSZ" >&2
    exit 1
fi

python3 manage.py verifier_reprise "$1"
