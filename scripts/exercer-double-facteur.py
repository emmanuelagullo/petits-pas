#!/usr/bin/env python3
"""Exerce le second facteur (TOTP) contre l'application réellement démarrée.

Utilisé par scripts/exercer-deploiement-ephemere.sh, avec PostgreSQL : il
vérifie par HTTP ce que les tests unitaires ne voient pas (processus réel,
cookies sécurisés derrière un proxy, plafond de saisies conservé par le
serveur, verrous de ligne de PostgreSQL), puis contrôle la base.

Le code TOTP est recalculé ici avec la bibliothèque standard seule, sans
rien importer de l'application : si l'application et une application
d'authentification standard divergeaient, ce scénario échouerait.

Le compte visé ne doit avoir aucun second facteur au départ ; il n'en a plus
à l'arrivée. Ne l'utiliser que sur un environnement jetable.
"""
import argparse
import base64
import hashlib
import hmac
import http.client
import os
import re
import struct
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode, urlparse

PAS = 30
RACINE_DU_PROJET = Path(__file__).resolve().parent.parent
CODES_SECOURS = re.compile(r"<code>([A-Z2-9]{4}(?:-[A-Z2-9]{4}){3})</code>")
CLE_SAISIE = re.compile(r"<code>([A-Z2-7]{4}(?: [A-Z2-7]{4}){7})</code>")
JETON_CSRF = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


def echec(message):
    print(f"ÉCHEC : {message}", file=sys.stderr)
    raise SystemExit(1)


def verifier(condition, message):
    if not condition:
        echec(message)
    print(f"  ok : {message}")


def code_totp(cle_base32, instant):
    """RFC 6238 : HMAC-SHA1, pas de 30 s, six chiffres."""
    cle = base64.b32decode(cle_base32 + "=" * (-len(cle_base32) % 8))
    condensat = hmac.new(cle, struct.pack(">Q", int(instant // PAS)), hashlib.sha1).digest()
    decalage = condensat[-1] & 0x0F
    nombre = struct.unpack(">I", condensat[decalage:decalage + 4])[0] & 0x7FFFFFFF
    return f"{nombre % 1_000_000:06d}"


class Client:
    """Navigateur minimal : sans suivi des redirections, cookies conservés à la
    main (le cookie de session est « Secure » alors que la CI parle en HTTP
    derrière un en-tête X-Forwarded-Proto)."""

    def __init__(self, url):
        analyse = urlparse(url)
        self.hote, self.port = analyse.hostname, analyse.port or 80
        self.cookies = {}

    def requete(self, methode, chemin, donnees=None, referer="/connexion/"):
        entetes = {
            "Host": f"{self.hote}:{self.port}",
            "X-Forwarded-Proto": "https",
            "Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
        }
        corps = None
        if donnees is not None:
            corps = urlencode(donnees)
            entetes["Content-Type"] = "application/x-www-form-urlencoded"
            entetes["Referer"] = f"https://{self.hote}:{self.port}{referer}"
            entetes["Origin"] = f"https://{self.hote}:{self.port}"
        connexion = http.client.HTTPConnection(self.hote, self.port, timeout=30)
        try:
            connexion.request(methode, chemin, body=corps, headers=entetes)
            reponse = connexion.getresponse()
            texte = reponse.read().decode("utf-8", "replace")
            for valeur in reponse.msg.get_all("Set-Cookie") or []:
                cookie = SimpleCookie(valeur)
                for nom, morceau in cookie.items():
                    if morceau.value == "" or morceau["max-age"] == "0":
                        self.cookies.pop(nom, None)
                    else:
                        self.cookies[nom] = morceau.value
            return reponse.status, reponse.getheader("Location") or "", texte
        finally:
            connexion.close()

    def lire(self, chemin):
        return self.requete("GET", chemin)

    def envoyer(self, chemin, donnees, referer=None):
        """POST avec le jeton CSRF de la page, lue au préalable."""
        _, _, page = self.lire(chemin)
        jeton = JETON_CSRF.search(page)
        if not jeton:
            echec(f"aucun jeton CSRF sur {chemin}")
        return self.requete(
            "POST", chemin, {**donnees, "csrfmiddlewaretoken": jeton.group(1)}, referer or chemin)


def se_connecter(client, utilisateur, mot_de_passe):
    return client.envoyer("/connexion/", {"nom_utilisateur": utilisateur, "mot_de_passe": mot_de_passe})


def sans_session(client):
    """Vrai si l'accueil renvoie vers la connexion : aucune session ouverte."""
    statut, lieu, _ = client.lire("/")
    return statut == 302 and "/connexion/" in lieu


def deconnecter(client):
    client.lire("/deconnexion/")
    client.cookies.pop("sessionid", None)


def demarrer_django():
    """Lancé comme « python3 scripts/... », la racine du projet n'est pas sur le chemin."""
    sys.path.insert(0, str(RACINE_DU_PROJET))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carnet.settings")
    import django

    django.setup()


def controler_base(utilisateur, cle_base32, codes_en_clair):
    """La clé n'est jamais en clair en base ; les codes de secours y sont des empreintes."""
    demarrer_django()
    from comptes.models import CodeSecoursDoubleFacteur, DoubleFacteurCompte

    compte = DoubleFacteurCompte.objects.get(utilisateur__username=utilisateur)
    verifier(compte.confirme_le is not None and compte.cle_chiffree, "inscription confirmée en base")
    verifier(cle_base32 not in compte.cle_chiffree, "la clé secrète n'est pas en clair en base")
    empreintes = list(CodeSecoursDoubleFacteur.objects.filter(
        utilisateur__username=utilisateur).values_list("empreinte", flat=True))
    verifier(len(empreintes) == 10 and all(len(e) == 64 for e in empreintes),
             "dix codes de secours conservés sous forme d'empreintes")
    verifier(not any(c.replace("-", "") in e for c in codes_en_clair for e in empreintes),
             "aucun code de secours en clair en base")


def reinitialiser_par_commande(utilisateur):
    demarrer_django()
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    from comptes.models import CodeSecoursDoubleFacteur, DoubleFacteurCompte

    get_user_model().objects.get_or_create(
        username="operateur-ci", defaults={"is_staff": True, "is_active": True})
    call_command("reinitialiser_double_facteur", utilisateur=utilisateur,
                 operateur="operateur-ci", motif="exercice de déploiement")
    compte = DoubleFacteurCompte.objects.filter(utilisateur__username=utilisateur).first()
    verifier(compte is None or (not compte.cle_chiffree and compte.confirme_le is None),
             "la réinitialisation par commande a effacé la clé")
    verifier(not CodeSecoursDoubleFacteur.objects.filter(utilisateur__username=utilisateur).exists(),
             "la réinitialisation par commande a effacé les codes de secours")


def scenario(url, utilisateur, mot_de_passe, plafond_maximal):
    client = Client(url)

    print("Inscription")
    verifier(se_connecter(client, utilisateur, mot_de_passe)[0] == 302, "connexion par mot de passe seul")
    statut, _, _ = client.lire("/")
    verifier(statut == 200, "l'accueil est accessible avant toute inscription")
    statut, _, page = client.lire("/mon-compte/double-facteur/")
    verifier(statut == 200 and "<svg" in page, "la page d'inscription affiche le QR code")
    cle = CLE_SAISIE.search(page)
    verifier(cle is not None, "la clé à saisir à la main est affichée")
    cle_base32 = cle.group(1).replace(" ", "")
    statut, _, page = client.envoyer("/mon-compte/double-facteur/", {"code": "000000"})
    verifier(statut == 200 and "Code incorrect" in page, "un code faux est refusé à l'inscription")
    maintenant = time.time()
    statut, _, page = client.envoyer("/mon-compte/double-facteur/", {"code": code_totp(cle_base32, maintenant)})
    verifier(statut == 200 and "Vos codes de secours" in page, "un code valide confirme l'inscription")
    codes = CODES_SECOURS.findall(page)
    verifier(len(set(codes)) == 10, "dix codes de secours distincts sont affichés")
    controler_base(utilisateur, cle_base32, codes)

    print("Connexion en deux étapes")
    deconnecter(client)
    statut, lieu, _ = se_connecter(client, utilisateur, mot_de_passe)
    verifier(statut == 302 and "/connexion/verification/" in lieu, "le mot de passe mène à la vérification")
    verifier(sans_session(client), "aucune session n'est ouverte avant le second facteur")
    statut, _, page = client.envoyer("/connexion/verification/", {"code": "000000"})
    verifier(statut == 200 and "Code incorrect" in page and sans_session(client), "un code faux ne connecte pas")
    # Le pas de la confirmation est consommé : le suivant est accepté (tolérance d'un pas).
    code = code_totp(cle_base32, time.time() + PAS)
    statut, lieu, _ = client.envoyer("/connexion/verification/", {"code": code})
    verifier(statut == 302 and "verification" not in lieu, "un code valide ouvre la session")
    verifier(client.lire("/")[0] == 200, "l'accueil est accessible après le second facteur")

    print("Rejeu et codes de secours")
    deconnecter(client)
    se_connecter(client, utilisateur, mot_de_passe)
    statut, _, page = client.envoyer("/connexion/verification/", {"code": code})
    verifier(statut == 200 and "Code incorrect" in page and sans_session(client),
             "un code déjà utilisé est refusé (pas de rejeu)")
    statut, lieu, _ = client.envoyer("/connexion/verification/", {"code": codes[0].lower()})
    verifier(statut == 302 and "verification" not in lieu, "un code de secours ouvre la session")
    _, _, page = client.lire("/")
    verifier("Un code de secours a été utilisé" in page, "la personne est prévenue de l'usage du code de secours")
    deconnecter(client)
    se_connecter(client, utilisateur, mot_de_passe)
    statut, _, page = client.envoyer("/connexion/verification/", {"code": codes[0]})
    verifier(statut == 200 and "Code incorrect" in page, "un code de secours ne sert qu'une fois")

    print("Plafond de saisies (conservé par le processus du serveur)")
    for tentative in range(1, plafond_maximal + 1):
        statut, _, _ = client.envoyer("/connexion/verification/", {"code": "000000"})
        if statut == 429:
            break
    verifier(statut == 429, f"les saisies sont plafonnées (429 atteint en {tentative} tentative(s) supplémentaire(s))")
    verifier(sans_session(client), "le plafond atteint ne connecte personne")

    print("Réinitialisation par le déployeur")
    reinitialiser_par_commande(utilisateur)
    deconnecter(client)
    statut, lieu, _ = se_connecter(client, utilisateur, mot_de_passe)
    verifier(statut == 302 and "verification" not in lieu,
             "après réinitialisation, plus de second facteur demandé tant que rien n'est obligatoire")
    verifier(client.lire("/")[0] == 200, "la personne se reconnecte avec son seul mot de passe")
    print("Second facteur exercé de bout en bout.")


def main():
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--url", default="http://127.0.0.1:8000")
    parseur.add_argument("--utilisateur", required=True)
    parseur.add_argument("--mot-de-passe", required=True)
    parseur.add_argument(
        "--plafond-maximal", type=int, default=25,
        help="nombre maximal de saisies fausses avant d'attendre le plafond (429)")
    options = parseur.parse_args()
    scenario(options.url, options.utilisateur, options.mot_de_passe, options.plafond_maximal)


if __name__ == "__main__":
    main()
