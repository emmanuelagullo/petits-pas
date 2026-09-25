#!/usr/bin/env bash
# Lister, rétablir ou nettoyer les versions installées (sans toucher aux données).
set -euo pipefail
racine="${XDG_DATA_HOME:-$HOME/.local/share}/petits-pas/programmes"
lanceur="${XDG_DATA_HOME:-$HOME/.local/share}/applications/petits-pas.desktop"
if [[ ! -f "$racine/actuelle" ]]; then
    printf 'Aucune installation Petits Pas trouvée.\n' >&2
    exit 1
fi
actuelle=$(<"$racine/actuelle")
precedente=''
[[ ! -f "$racine/precedente" ]] || precedente=$(<"$racine/precedente")
valide() { [[ "$1" =~ ^[0-9a-f]{16}$ && -x "$racine/$1/PetitsPas" && ! -L "$racine/$1" ]]; }
valide "$actuelle" || { printf 'Version actuelle invalide.\n' >&2; exit 1; }

case "${1:---lister}" in
    --lister)
        printf 'Version active : %s\n' "$actuelle"
        [[ -z "$precedente" ]] || printf 'Version précédente : %s\n' "$precedente"
        for dossier in "$racine"/*; do
            [[ -d "$dossier" && ! -L "$dossier" ]] || continue
            identifiant=${dossier##*/}
            [[ "$identifiant" =~ ^[0-9a-f]{16}$ ]] || continue
            printf 'Installée : %s\n' "$identifiant"
        done
        ;;
    --revenir)
        if ! valide "$precedente"; then
            printf 'Aucune version précédente disponible.\n' >&2
            exit 1
        fi
        sed "s|^Exec=.*|Exec=\"$racine/$precedente/PetitsPas\"|" "$lanceur" > "$lanceur.tmp"
        mv -- "$lanceur.tmp" "$lanceur"
        printf '%s\n' "$actuelle" > "$racine/precedente"
        printf '%s\n' "$precedente" > "$racine/actuelle"
        printf 'Lanceur revenu à la version %s. Fermez toute fenêtre encore ouverte avant de relancer.\n' "$precedente"
        ;;
    --nettoyer)
        for dossier in "$racine"/*; do
            [[ -d "$dossier" && ! -L "$dossier" ]] || continue
            identifiant=${dossier##*/}
            [[ "$identifiant" =~ ^[0-9a-f]{16}$ ]] || continue
            if [[ "$identifiant" != "$actuelle" && "$identifiant" != "$precedente" ]]; then
                rm -rf -- "$dossier"
                printf 'Ancienne version supprimée : %s\n' "$identifiant"
            fi
        done
        ;;
    *) printf 'Usage : %s [--lister|--revenir|--nettoyer]\n' "$0" >&2; exit 2 ;;
esac
