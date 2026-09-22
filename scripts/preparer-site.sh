#!/usr/bin/env bash
# Prépare les contenus générés du site sans modifier leurs sources de référence.
set -euo pipefail

racine=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
destination="$racine/site/content/conception/documents"

documents=(
    "POLITIQUE-AUTORISATION.org:politique-autorisation.org"
    "MODELE-IDENTITES-ET-AFFECTATIONS.org:modele-identites-et-affectations.org"
    "MATRICE-AUTORISATIONS.org:matrice-autorisations.org"
    "PLAN-IMPLEMENTATION-AUTORISATIONS.org:plan-implementation-autorisations.org"
)

mkdir -p "$destination"
find "$destination" -maxdepth 1 -type f -name '*.org' -delete

for entree in "${documents[@]}"; do
    source=${entree%%:*}
    cible=${entree#*:}
    if [[ ! -r "$racine/$source" ]]; then
        echo "Document public introuvable : $source" >&2
        exit 1
    fi
    cp "$racine/$source" "$destination/$cible"
done

echo "Documents Org publics préparés dans ${destination#"$racine/"}/."
