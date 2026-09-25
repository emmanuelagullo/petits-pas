#!/usr/bin/env bash
# Publier les archives validées après création et poussée du même tag Git.
set -euo pipefail

if { (( $# != 2 && $# != 5 )) || [[ ! "$1" =~ ^[0-9]+$ ]] || [[ ! "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; }; then
    printf 'Usage : %s RUN_ID TAG [ARCHIVE_LINUX ARCHIVE_WINDOWS SHA_DU_RUN]\n' "$0" >&2
    exit 2
fi
run_id=$1
tag=$2
depot=emmanuelagullo/petits-pas
gitlab=https://gitlab.inria.fr/petits-pas/petits-pas
github=https://github.com/$depot

for programme in git python3; do
    command -v "$programme" >/dev/null || { printf '%s est requis.\n' "$programme" >&2; exit 1; }
done
avec_gh=false
avec_glab=false
if command -v gh >/dev/null; then avec_gh=true; fi
if command -v glab >/dev/null; then avec_glab=true; fi

instructions_github() {
    printf '\nGitHub (interface web) : %s/releases/new\n' "$github"
    printf 'Choisir le tag existant %s, joindre PetitsPas-linux.tar.gz et PetitsPas-windows.zip (les archives intérieures de l’exécution %s), cocher « pre-release », puis publier.\n' "$tag" "$run_id"
}
instructions_gitlab() {
    printf '\nGitLab (interface web) : %s/-/releases/new\n' "$gitlab"
    printf 'Choisir le tag existant %s, donner le même titre et les mêmes notes, puis ajouter deux liens de ressources (« Asset links ») :\n' "$tag"
    printf '  Linux   : %s/releases/download/%s/PetitsPas-linux.tar.gz\n' "$github" "$tag"
    printf '  Windows : %s/releases/download/%s/PetitsPas-windows.zip\n' "$github" "$tag"
    printf 'Ces liens pointent vers les archives hébergées sur GitHub ; les héberger aussi sur GitLab nécessite un chargement distinct dans son registre de paquets.\n'
}

if ! $avec_gh && ! $avec_glab; then
    printf 'Avertissement : ni gh ni glab ne sont disponibles ; aucune release ne sera créée.\n' >&2
    printf 'Télécharger les artefacts de l’exécution %s depuis %s/actions/runs/%s ; décompresser les ZIP enveloppes.\n' "$run_id" "$github" "$run_id"
    instructions_github
    instructions_gitlab
    exit 1
fi
if ! $avec_gh; then
    printf 'Avertissement : gh absent ; seule la release GitLab peut être automatisée avec des archives déjà téléchargées.\n' >&2
    if (( $# != 5 )) || [[ ! "$5" =~ ^[0-9a-fA-F]{40}$ ]]; then
        printf 'Télécharger les deux archives depuis %s/actions/runs/%s, noter le SHA du commit indiqué par GitHub Actions, puis relancer :\n  bash %s %s %s CHEMIN/PetitsPas-linux.tar.gz CHEMIN/PetitsPas-windows.zip SHA_DU_RUN\n' "$github" "$run_id" "$0" "$run_id" "$tag" >&2
        instructions_github
        exit 2
    fi
fi
if ! $avec_glab; then
    printf 'Avertissement : glab absent ; seule la release GitHub sera publiée automatiquement.\n' >&2
fi

if $avec_gh; then
    informations=$(gh run view "$run_id" --repo "$depot" --json conclusion,headSha,workflowName)
    sha=$(python3 -c '
import json, sys
run = json.load(sys.stdin)
if run["conclusion"] != "success" or run["workflowName"] != "Paquets autonomes Linux et Windows (prototype)":
    raise SystemExit("Choisissez une exécution réussie du workflow des paquets autonomes.")
print(run["headSha"])
' <<< "$informations")
else
    sha=${5,,}
    printf 'Vérifiez dans GitHub Actions que l’exécution %s est réussie et indique le commit %s.\n' "$run_id" "$sha"
fi

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
if (( $# == 5 )); then
    linux=$(realpath -- "$3")
    windows=$(realpath -- "$4")
    if [[ "$linux" != */PetitsPas-linux.tar.gz || "$windows" != */PetitsPas-windows.zip ]]; then
        printf 'Noms attendus : PetitsPas-linux.tar.gz et PetitsPas-windows.zip.\n' >&2
        exit 1
    fi
    if $avec_gh && [[ "${5,,}" != "$sha" ]]; then
        printf 'Le SHA du run fourni ne correspond pas au SHA vérifié par gh.\n' >&2
        exit 1
    fi
else
    gh run download "$run_id" --repo "$depot" --name PetitsPas-linux --dir "$temporaire/linux"
    gh run download "$run_id" --repo "$depot" --name PetitsPas-windows --dir "$temporaire/windows"
    linux="$temporaire/linux/PetitsPas-linux.tar.gz"
    windows="$temporaire/windows/PetitsPas-windows.zip"
fi

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

Téléchargement et installation : https://petits-pas.gitlabpages.inria.fr/petits-pas/guide/local/telecharger-programme/

Source : commit $sha ; exécution GitHub Actions $run_id.
EOF

printf 'Exécution : %s\nCommit et tags vérifiés : %s\nTag : %s\n' "$run_id" "$sha" "$tag"
if $avec_gh; then
    printf 'Archives vérifiées. Création du brouillon GitHub…\n'
    gh release create "$tag" "$linux" "$windows" --repo "$depot" \
        --verify-tag --draft --prerelease --latest=false \
        --title "Petits Pas $tag (test)" --notes-file "$temporaire/notes.md"
fi
if $avec_glab; then
    printf 'Publication de la release GitLab avec les mêmes archives…\n'
    glab release create "$tag" "$linux" "$windows" --repo "$gitlab" \
        --no-update --use-package-registry \
        --name "Petits Pas $tag (test)" --notes-file "$temporaire/notes.md"
fi
if $avec_gh; then
    printf 'Publication du brouillon GitHub…\n'
    gh release edit "$tag" --repo "$depot" --draft=false
fi
if ! $avec_gh; then instructions_github; fi
if ! $avec_glab; then instructions_gitlab; fi
printf 'Publication automatisée terminée pour le tag %s et le commit %s.\n' "$tag" "$sha"
