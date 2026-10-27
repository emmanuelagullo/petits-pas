#!/usr/bin/env bash
# Diagnostiquer un plantage natif de PetitsPas.app en CI (SIGBUS, SIGSEGV) : à lancer après un échec.
# Chaque commande tolère l'échec : ce script n'a pour but que d'afficher des indices.
set -uo pipefail
cd "$(dirname "$0")/.."
programme="dist/PetitsPas.app/Contents/MacOS/PetitsPas"
[ -x "$programme" ] || { echo "Programme absent : $programme"; exit 0; }

echo "::group::Sortie directe avec trace Python"
PYTHONFAULTHANDLER=1 "$programme" --verifier-distribution 2>&1 | tail -80
echo "code de sortie : ${PIPESTATUS[0]}"
echo "::endgroup::"

echo "::group::Dernières bibliothèques chargées avant la fin"
DYLD_PRINT_LIBRARIES=1 "$programme" --verifier-distribution 2>&1 | grep -i "dylib\|\.so\|Framework" | tail -25
echo "::endgroup::"

echo "::group::Pile native sous lldb"
sudo DevToolsSecurity -enable >/dev/null 2>&1
timeout 240 lldb --batch -o "process launch -- --verifier-distribution" -o "bt 30" -o "thread list" -- "$programme" 2>&1 | tail -70
echo "::endgroup::"

echo "::group::Rapports de plantage système"
sleep 20
dossier="$HOME/Library/Logs/DiagnosticReports"
ls -la "$dossier" 2>/dev/null | tail -12
for rapport in "$dossier"/PetitsPas*.ips; do
    [ -f "$rapport" ] || continue
    echo "=== $rapport"
    python3 - "$rapport" <<'PYRAPPORT'
import json, sys
texte = open(sys.argv[1], encoding="utf-8", errors="replace").read()
corps = json.loads(texte.split("\n", 1)[1]) if "\n" in texte else {}
print("exception :", corps.get("exception"))
print("termination :", corps.get("termination"))
images = corps.get("usedImages", [])
for numero, fil in enumerate(corps.get("threads", [])):
    if fil.get("triggered"):
        print("fil fautif :", numero, fil.get("name", ""))
        for trame in fil.get("frames", [])[:25]:
            image = images[trame["imageIndex"]]["name"] if trame.get("imageIndex") is not None else "?"
            print("  ", image, trame.get("symbol", ""), trame.get("imageOffset", ""))
PYRAPPORT
done
echo "::endgroup::"
exit 0
