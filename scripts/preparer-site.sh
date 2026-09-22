#!/bin/sh
# Prépare les contenus générés du site sans modifier leurs sources de référence.
set -eu

racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination="$racine/site/content/conception/documents"

mkdir -p "$destination"
find "$destination" -maxdepth 1 -type f -name '*.org' -delete

while IFS=: read -r source cible; do
    if [ ! -r "$racine/$source" ]; then
        echo "Document public introuvable : $source" >&2
        exit 1
    fi
    cp "$racine/$source" "$destination/$cible"
done <<'EOF'
POLITIQUE-AUTORISATION.org:politique-autorisation.org
MODELE-IDENTITES-ET-AFFECTATIONS.org:modele-identites-et-affectations.org
MATRICE-AUTORISATIONS.org:matrice-autorisations.org
PLAN-IMPLEMENTATION-AUTORISATIONS.org:plan-implementation-autorisations.org
EOF

echo "Documents Org publics préparés dans ${destination#"$racine/"}/."
