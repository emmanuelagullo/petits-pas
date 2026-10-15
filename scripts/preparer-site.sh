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

# Associations explicites et anciennes éditions, pour une adoption reproductible.
cp "$racine/referentiel/images-proposees/associations-im4.yaml" "$contenus/ASSOCIATIONS-IM4.yaml"
cp "$racine/referentiel/images-proposees/associations-im4.yaml" "$chatdecole/ASSOCIATIONS-IM4.yaml"
mkdir -p "$contenus/editions" "$chatdecole/editions"
cp "$racine/referentiel/cycle1/editions/"*.yaml "$contenus/editions/"
cp "$racine/referentiel/chatdecole/editions/"*.yaml "$chatdecole/editions/"

# Collection d'images et planche communes aux offres.
images="$racine/site/static/referentiels/images-proposees"
mkdir -p "$images"
for source in collection-im5.yaml planche-im5.svg; do
    cp "$racine/referentiel/images-proposees/$source" "$images/$source"
done

cp "$racine/referentiel/images-proposees/associations-im6.yaml" "$contenus/ASSOCIATIONS-IM6.yaml"
cp "$racine/referentiel/images-proposees/associations-im6.yaml" "$chatdecole/ASSOCIATIONS-IM6.yaml"
