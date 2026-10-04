#!/usr/bin/env bash
# Publier sur GitHub les fichiers du tag déjà construits et contrôlés.
set -euo pipefail
exec python3 "$(dirname "$0")/publier-paquets.py" "$@"
