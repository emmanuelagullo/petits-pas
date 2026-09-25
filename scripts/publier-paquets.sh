#!/usr/bin/env bash
# Publier sur les deux forges après création et poussée du même tag Git.
set -euo pipefail

if (( $# != 2 )) || [[ ! "$1" =~ ^[0-9]+$ ]] || [[ ! "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    printf 'Usage : %s RUN_ID TAG\n' "$0" >&2
    exit 2
fi
run_id=$1
tag=$2
depot=emmanuelagullo/petits-pas
gitlab=https://gitlab.inria.fr/petits-pas/petits-pas

for programme in gh glab git python3; do
    command -v "$programme" >/dev/null || { printf '%s est requis.\n' "$programme" >&2; exit 1; }
done

informations=$(gh run view "$run_id" --repo "$depot" --json conclusion,headSha,workflowName)
sha=$(python3 -c '
import json, sys
run = json.load(sys.stdin)
if run["conclusion"] != "success" or run["workflowName"] != "Paquets autonomes Linux et Windows (prototype)":
    raise SystemExit("Choisissez une exécution réussie du workflow des paquets autonomes.")
print(run["headSha"])
' <<< "$informations")

# Vérifier le tag local et ses deux copies avant de publier quoi que ce soit.
local_sha=$(git rev-parse --verify "refs/tags/$tag^{}")
if [[ "$local_sha" != "$sha" ]]; then
    printf 'Le tag local pointe sur %s mais les archives viennent de %s.\n' "$local_sha" "$sha" >&2
    exit 1
fi
for depot_git in inria github; do
    distance=$(git ls-remote --tags "$depot_git" "refs/tags/$tag^{}" | cut -f1)
    if [[ -z "$distance" ]]; then
        distance=$(git ls-remote --tags "$depot_git" "refs/tags/$tag" | cut -f1)
    fi
    if [[ "$distance" != "$sha" ]]; then
        printf 'Tag %s absent ou différent sur %s (attendu : %s).\n' "$tag" "$depot_git" "$sha" >&2
        exit 1
    fi
done

temporaire=$(mktemp -d)
trap 'rm -rf -- "$temporaire"' EXIT
gh run download "$run_id" --repo "$depot" --name PetitsPas-linux --dir "$temporaire/linux"
gh run download "$run_id" --repo "$depot" --name PetitsPas-windows --dir "$temporaire/windows"
linux="$temporaire/linux/PetitsPas-linux.tar.gz"
windows="$temporaire/windows/PetitsPas-windows.zip"

python3 - "$linux" "$windows" <<'PY'
import sys
import tarfile
import zipfile
from pathlib import Path

linux, windows = map(Path, sys.argv[1:])
with tarfile.open(linux, "r:gz") as archive:
    if not any(entree.name == "PetitsPas/PetitsPas" for entree in archive):
        raise SystemExit("Exécutable Linux absent de l'archive.")
with zipfile.ZipFile(windows) as archive:
    if archive.testzip() is not None or not any(
        nom.endswith("/PetitsPas.exe") or nom == "PetitsPas.exe"
        for nom in archive.namelist()
    ):
        raise SystemExit("Archive Windows incomplète ou endommagée.")
PY

cat > "$temporaire/notes.md" <<EOF
Version de test de Petits Pas (application autonome, sans serveur externe).

- Windows : décompresser intégralement PetitsPas-windows.zip et lancer PetitsPas.exe.
- Linux : extraire PetitsPas-linux.tar.gz et lancer PetitsPas/PetitsPas sur Ubuntu 24.04 avec GTK, WebKit2 et Pango installés. Compatibilité Guix non validée.
- Les données (base SQLite et médias) sont conservées séparément des exécutables.

Source : commit $sha ; exécution GitHub Actions $run_id.
EOF

printf 'Exécution : %s\nCommit et tags vérifiés : %s\nTag : %s\n' "$run_id" "$sha" "$tag"
printf 'Archives vérifiées. Création du brouillon GitHub…\n'
gh release create "$tag" "$linux" "$windows" --repo "$depot" \
    --verify-tag --draft --prerelease --latest=false \
    --title "Petits Pas $tag (test)" --notes-file "$temporaire/notes.md"
printf 'Publication de la release GitLab avec les mêmes archives…\n'
glab release create "$tag" "$linux" "$windows" --repo "$gitlab" \
    --no-update --use-package-registry \
    --name "Petits Pas $tag (test)" --notes-file "$temporaire/notes.md"
printf 'Publication du brouillon GitHub…\n'
gh release edit "$tag" --repo "$depot" --draft=false
printf 'Deux releases publiées pour le même tag %s et le même commit %s.\n' "$tag" "$sha"
