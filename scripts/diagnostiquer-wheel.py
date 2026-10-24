"""Sondes HTTP sans dépendance ni installation ; ne remplace pas pip."""
import hashlib
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


HEADERS = ("Server", "Via", "Age", "X-Cache", "X-Cache-Hits",
           "X-GitHub-Request-Id", "X-Served-By", "Content-Type")


def origine(url):
    # Ne jamais journaliser une URL signée de release ni des identifiants proxy.
    p = urllib.parse.urlsplit(url)
    return p.hostname or "inconnue"


class Redirections(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        print(f"  redirection HTTP {code} : {origine(req.full_url)} → {origine(newurl)}", flush=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def sonder(nom, url, empreinte=None, sans_cache=False):
    print(f"\n{nom} ({origine(url)})", flush=True)
    headers = {"User-Agent": "petits-pas-diagnostic-wheel"}
    if sans_cache:
        headers["Cache-Control"] = "no-cache"
    req = urllib.request.Request(url, headers=headers)
    debut = time.monotonic()
    try:
        try:
            reponse = urllib.request.build_opener(Redirections()).open(req, timeout=20)
        except urllib.error.HTTPError as erreur:
            reponse = erreur
        with reponse:
            print(f"  HTTP {reponse.code}, hôte final : {origine(reponse.url)}")
            for cle in HEADERS:
                if cle in reponse.headers:
                    print(f"  {cle}: {reponse.headers[cle]}")
            # Aucun corps d’erreur ni en-tête Location/Set-Cookie dans le journal.
            if reponse.code != 200:
                return False
            contenu = reponse.read(4 * 1024 * 1024 + 1)
            if empreinte:
                digest = hashlib.sha256(contenu).hexdigest()
                print(f"  {len(contenu)} octets ; SHA-256 {digest}")
                print(f"  empreinte attendue : {digest == empreinte}")
                return digest == empreinte
            return True
    except (OSError, urllib.error.URLError) as erreur:
        # Le message brut peut contenir l’URL signée ou un proxy authentifié.
        print(f"  erreur de transport : {type(erreur).__name__}")
        return False
    finally:
        print(f"  durée : {time.monotonic() - debut:.1f} s", flush=True)


def main():
    ligne = next(l for l in Path("requirements-communs.txt").read_text().splitlines()
                 if l.startswith("pas-communs"))
    url = ligne.split("@", 1)[1].strip()
    url, fragment = urllib.parse.urldefrag(url)
    empreinte = urllib.parse.parse_qs(fragment)["sha256"][0]
    if not re.fullmatch(r"[a-f0-9]{64}", empreinte):
        raise ValueError("Empreinte SHA-256 invalide")
    print("Python :", sys.version.split()[0])
    print("Variables proxy présentes :", ", ".join(sorted(
        k for k in os.environ if k.lower() in
        {"http_proxy", "https_proxy", "all_proxy", "no_proxy"})) or "aucune")
    for hote in ("github.com", "release-assets.githubusercontent.com", "pypi.org"):
        try:
            adresses = sorted({r[4][0] for r in socket.getaddrinfo(hote, 443)})
            print(f"DNS {hote} : {', '.join(adresses)}")
        except OSError as erreur:
            print(f"DNS {hote} : {type(erreur).__name__}")
    sonder("Témoin PyPI", "https://pypi.org/simple/pip/")
    sonder("Témoin GitHub", "https://github.com/")
    exact = sonder("Wheel : URL exacte utilisée par pip", url, empreinte)
    # Sonde comparative uniquement : ne modifie jamais requirements ni pip.
    variante = url + ("&" if "?" in url else "?") + "diagnostic=" + str(time.time_ns())
    autre = sonder("Wheel : requête distincte avec no-cache", variante, empreinte, True)
    print(f"\nBilan : URL exacte conforme={exact} ; requête distincte conforme={autre}")
    print("Cette sonde ne qualifie pas l’application et ne remplace aucun test.")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
