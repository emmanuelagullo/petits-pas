#!/usr/bin/env bash
# Installer une archive extraite pour l'utilisateur courant (Ubuntu).
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ! -f "$source_dir/PetitsPas" || ! -d "$source_dir/_internal" ]]; then
    printf 'Dossier PetitsPas incomplet : %s\n' "$source_dir" >&2
    exit 1
fi

# Inclure aussi les ressources Django et les bibliothèques dans la version.
empreinte=$(cd "$source_dir" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
racine="${XDG_DATA_HOME:-$HOME/.local/share}/petits-pas/programmes"
destination="$racine/$empreinte"
mkdir -p "$racine"
if [[ ! -e "$destination" ]]; then
    etape=$(mktemp -d "$racine/.installation-XXXXXXXX")
    trap 'rm -rf -- "$etape"' EXIT
    cp -a "$source_dir/." "$etape/"
    mv -- "$etape" "$destination"
    trap - EXIT
fi

if [[ ! -x "$destination/PetitsPas" ]]; then
    printf 'Installation incomplète : %s\n' "$destination" >&2
    exit 1
fi

applications="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$applications"
cat > "$applications/petits-pas.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Petits Pas
Comment=Carnet de suivi des apprentissages
Exec="$destination/PetitsPas"
Terminal=true
Categories=Education;
EOF
printf 'Application installée : %s\nLanceur : %s/petits-pas.desktop\n' "$destination" "$applications"
printf 'Les données de l’école restent dans le paquet autonome, séparé du programme.\n'
