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

# Publication explicite des contenus cycle 1, depuis leurs seules sources.
contenus="$racine/site/static/referentiels/cycle1"
mkdir -p "$contenus/illustrations"
for source in objectifs-programmes.yaml cycle1-etaye.yaml REGISTRE.csv NOTICE.org COUVERTURE.org EMPREINTES.org; do
    cp "$racine/referentiel/cycle1/$source" "$contenus/$source"
done
cp "$racine/referentiel/REGISTRE-CONTENUS-CR2.org" "$contenus/REGISTRE-CONTENUS-CR2.org"
for source in ILLUSTRATIONS-CR5.org ILLUSTRATIONS-CR5.yaml ASSOCIATIONS-CR5.yaml; do
    cp "$racine/referentiel/$source" "$contenus/$source"
done
cp "$racine/referentiel/static/referentiel/icones/openmoji/"*.svg "$contenus/illustrations/"
cp "$racine/referentiel/static/referentiel/icones/openmoji/LICENSE.txt" "$contenus/illustrations/LICENSE.txt"

chatdecole="$racine/site/static/referentiels/chatdecole"
mkdir -p "$chatdecole"
for source in tableaux-cycle1.yaml NOTICE.org REGISTRE.csv; do
    cp "$racine/referentiel/chatdecole/$source" "$chatdecole/$source"
done

echo "Documents Org publics préparés dans ${destination#"$racine/"}/."
