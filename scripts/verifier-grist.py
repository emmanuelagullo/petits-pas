"""Vérifier Grist en lecture et écriture sur un document fictif dédié."""
import json
import os
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def verifier(url):
    adresse = urlsplit(url)
    chemin = re.fullmatch(r"(/o/[A-Za-z0-9_-]+)?/([A-Za-z0-9_-]{8,64})(?:/[^/]*)?/?", adresse.path, re.ASCII)
    if adresse.scheme != "https" or adresse.netloc != "grist.numerique.gouv.fr" or not chemin:
        raise ValueError("Lien de recette Grist invalide.")
    api = f"https://grist.numerique.gouv.fr{chemin[1] or ''}/api/docs/{chemin[2]}"
    table = "PetitsPasRecette" + uuid4().hex[:16]

    def appeler(chemin, methode="GET", corps=None):
        requete = Request(api + chemin, method=methode,
                          data=None if corps is None else json.dumps(corps).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(requete, timeout=15) as reponse:
            contenu = reponse.read()
        return json.loads(contenu) if contenu else None

    enregistrer = f"/tables/{table}/records"
    try:
        appeler("/tables", "POST", {"tables": [{"id": table, "columns": [
            {"id": cle, "fields": {"type": "Text"}} for cle in ("Identifiant", "Contenu")
        ]}]})
        identifiants = [str(uuid4()), str(uuid4())]
        for cle in identifiants:
            appeler(enregistrer + "?noparse=true&onmany=none", "PUT", {"records": [
                {"require": {"Identifiant": cle}, "fields": {"Contenu": "premier envoi"}}
            ]})
        appeler(enregistrer + "?noparse=true&onmany=none", "PUT", {"records": [
            {"require": {"Identifiant": identifiants[0]}, "fields": {"Contenu": "édition suivante"}}
        ]})
        filtre = urlencode({"filter": json.dumps({"Identifiant": [identifiants[0]]})})
        distant = appeler(enregistrer + "?" + filtre)["records"]
        if len(distant) != 1 or distant[0]["fields"]["Contenu"] != "édition suivante":
            raise RuntimeError("La relecture de la nouvelle édition a échoué.")
        if len(appeler(enregistrer)["records"]) != 2:
            raise RuntimeError("Les deux identifiants doivent rester distincts.")
    finally:
        if any(t["id"] == table for t in appeler("/tables")["tables"]):
            appeler("/apply", "POST", [["RemoveTable", table]])


if __name__ == "__main__":
    url = os.environ.get("PETITS_PAS_GRIST_ESSAI")
    if not url:
        raise SystemExit("Configurez PETITS_PAS_GRIST_ESSAI avec un document fictif dédié, ouvert en écriture.")
    try:
        verifier(url)
    except Exception as erreur:
        raise SystemExit(f"Recette Grist en échec ({type(erreur).__name__}).") from None
    print("Grist : écriture, mise à jour, lecture filtrée et nettoyage vérifiés.")
