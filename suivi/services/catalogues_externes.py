"""Lecture du format de catalogue Grist utilisé dans le pilote."""
import hashlib
import json
import re
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
from django.core.exceptions import ValidationError

from .import_sources_referentiels import identifiant, texte

HOTE_GRIST = "grist.numerique.gouv.fr"
CATALOGUE_DEMONSTRATION = f"https://{HOTE_GRIST}/o/docs/mrfW7gsAGMZbJdgP5djGva"
TAILLE_MAX = 1024 * 1024


def adresse_grist(valeur):
    try:
        adresse = urlsplit(valeur.strip())
    except ValueError as erreur:
        raise ValidationError("Le lien Grist est invalide.") from erreur
    chemin = re.fullmatch(r"(/o/([A-Za-z0-9_-]+))?/([A-Za-z0-9_-]{8,64})(?:/[^/]*)?/?", adresse.path)
    if adresse.scheme != "https" or adresse.netloc != HOTE_GRIST or not chemin:
        raise ValidationError("Collez le lien d’un document de grist.numerique.gouv.fr.")
    prefixe, _, document = chemin.groups()
    return prefixe or "", document


class SansRedirection(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def lire_api(prefixe, document, chemin=""):
    requete = Request(f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}{chemin}",
                      headers={"Accept": "application/json"})
    try:
        with build_opener(SansRedirection()).open(requete, timeout=5) as reponse:
            donnees = reponse.read(TAILLE_MAX + 1)
        if len(donnees) > TAILLE_MAX:
            raise ValidationError("Le catalogue Grist dépasse la taille admise pour cet essai.")
        return json.loads(donnees)
    except HTTPError as erreur:
        if erreur.code in (401, 403):
            raise ValidationError(
                "Ce catalogue demande un accès Grist. Ouvrez le document chez le fournisseur pour vérifier son partage."
            ) from erreur
        raise ValidationError("Ce catalogue Grist est indisponible.") from erreur
    except (OSError, HTTPException, ValueError) as erreur:
        raise ValidationError("La réponse du catalogue Grist est indisponible ou illisible.") from erreur


def lignes_grist(reponse):
    try:
        lignes = reponse["records"]
        if not isinstance(lignes, list) or any(not isinstance(ligne["fields"], dict) for ligne in lignes):
            raise TypeError
        return [ligne["fields"] for ligne in lignes]
    except (KeyError, TypeError) as erreur:
        raise ValidationError("Le tableau Grist n’a pas le format attendu.") from erreur


def lire_catalogue_grist(url):
    prefixe, document = adresse_grist(url)
    metadata = lire_api(prefixe, document)
    if not isinstance(metadata, dict):
        raise ValidationError("Les informations de ce document Grist sont illisibles.")
    nom = texte(metadata.get("name"), "Nom du catalogue")
    document = identifiant(metadata.get("id"), "Identifiant du document Grist", 64)
    url = f"https://{HOTE_GRIST}{prefixe}/{document}"
    referentiels = {}
    numeros = set()
    for ligne in lignes_grist(lire_api(prefixe, document, "/tables/Editions/records")):
        cle = identifiant(ligne.get("Referentiel"), "Identifiant du référentiel")
        titre = texte(ligne.get("Titre"), "Titre du référentiel")
        numero = ligne.get("Numero")
        if type(numero) is not int or numero < 1 or numero in numeros:
            raise ValidationError("Chaque édition du document Grist doit avoir un numéro entier positif distinct.")
        numeros.add(numero)
        source = referentiels.setdefault(cle, {"titre": titre, "editions": [], "reference": cle})
        if source["titre"] != titre:
            raise ValidationError("Utilisez le même titre pour les éditions d’un référentiel.")
        source["editions"].append(numero)
    if not referentiels:
        raise ValidationError("Ce catalogue Grist ne contient aucune édition.")
    for source in referentiels.values():
        source["editions"].sort(reverse=True)
    return {"url": url, "nom": nom, "referentiels": list(referentiels.values())}


def identite_grist(url, reference):
    _, document = adresse_grist(url)
    empreinte = hashlib.sha256(f"{HOTE_GRIST}/{document}/{reference}".encode()).hexdigest()
    return f"grist-{empreinte}"


def edition_grist(url, reference, numero):
    catalogue = lire_catalogue_grist(url)
    source = next((ligne for ligne in catalogue["referentiels"] if ligne["reference"] == reference), None)
    if not source or numero not in source["editions"]:
        raise ValidationError("Cette édition ne figure plus dans le catalogue Grist.")
    prefixe, document = adresse_grist(catalogue["url"])
    domaines = {}
    for ligne in lignes_grist(lire_api(prefixe, document, "/tables/Competences/records")):
        if ligne.get("Edition") != numero:
            continue
        rubrique = texte(ligne.get("Rubrique"), "Rubrique")
        code = identifiant(ligne.get("Code"), "Code de compétence", 20)
        domaine = domaines.setdefault(rubrique, {
            "code": hashlib.sha256(rubrique.encode()).hexdigest()[:20],
            "nom": rubrique, "competences": [],
        })
        domaine["competences"].append({"identite": code, "code": code, "libelle": ligne.get("Libelle")})
    return yaml.safe_dump({
        "format": 1, "version": str(numero),
        "source": {"identifiant": identite_grist(catalogue["url"], reference), "titre": source["titre"],
                   "provenance": f"Document Grist {HOTE_GRIST}/{document}",
                   "licence": "Non renseignée", "provisoire": True},
        "domaines": list(domaines.values()),
    }, allow_unicode=True)
