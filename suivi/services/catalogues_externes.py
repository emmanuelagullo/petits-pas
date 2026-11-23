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
    return requete_api(prefixe, document, chemin)


def requete_api(prefixe, document, chemin, *, corps=None, methode=None):
    headers = {"Accept": "application/json"}
    if corps is not None:
        headers["Content-Type"] = "application/json"
    requete = Request(f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}{chemin}",
                      data=corps, method=methode or ("PUT" if corps is not None else "GET"), headers=headers)
    try:
        with build_opener(SansRedirection()).open(requete, timeout=5) as reponse:
            donnees = reponse.read(TAILLE_MAX + 1)
        if len(donnees) > TAILLE_MAX:
            raise ValidationError("Le catalogue Grist dépasse la taille admise pour cet essai.")
        return json.loads(donnees) if donnees or corps is None else None
    except HTTPError as erreur:
        if erreur.code in (401, 403) and corps is not None:
            raise ValidationError("Grist n’autorise pas l’écriture dans ce document.") from erreur
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


def document_grist(url):
    prefixe, document = adresse_grist(url)
    metadata = lire_api(prefixe, document)
    if not isinstance(metadata, dict):
        raise ValidationError("Les informations de ce document Grist sont illisibles.")
    nom = texte(metadata.get("name"), "Nom du catalogue")
    document = identifiant(metadata.get("id"), "Identifiant du document Grist", 64)
    url = f"https://{HOTE_GRIST}{prefixe}/{document}"
    return prefixe, document, url, nom


def numerotation_grist_globale(lignes):
    """Les catalogues anciens relient Competences à Editions par le seul numéro."""
    return any(not ligne.get("Contenu") for ligne in lignes)


def referentiels_grist(lignes):
    referentiels = {}
    numeros = set()
    globale = numerotation_grist_globale(lignes)
    for ligne in lignes:
        cle = identifiant(ligne.get("Referentiel"), "Identifiant du référentiel")
        titre = texte(ligne.get("Titre"), "Titre du référentiel")
        numero = ligne.get("Numero")
        if type(numero) is not int or numero < 1:
            raise ValidationError("Chaque édition doit avoir un numéro entier positif.")
        cle_edition = numero if globale else (cle, numero)
        if cle_edition in numeros:
            raise ValidationError("Le catalogue contient des numéros d’édition en double. "
                                  "Les anciennes éditions sans Contenu exigent des numéros distincts dans tout le catalogue."
                                  if globale else "Deux éditions d’un même référentiel ont le même numéro.")
        numeros.add(cle_edition)
        source = referentiels.setdefault(cle, {"titre": titre, "editions": [], "reference": cle})
        if source["titre"] != titre:
            raise ValidationError("Utilisez le même titre pour les éditions d’un référentiel.")
        source["editions"].append(numero)
    for source in referentiels.values():
        source["editions"].sort(reverse=True)
    return list(referentiels.values())


def lire_catalogue_grist(url, *, avec_lignes=False):
    prefixe, document, url, nom = document_grist(url)
    lignes = lignes_grist(lire_api(prefixe, document, "/tables/Editions/records"))
    referentiels = referentiels_grist(lignes)
    if not referentiels:
        raise ValidationError("Ce catalogue Grist ne contient aucune édition.")
    resultat = {"url": url, "nom": nom, "referentiels": referentiels}
    return (resultat, lignes) if avec_lignes else resultat


def identite_grist(url, reference):
    _, document = adresse_grist(url)
    empreinte = hashlib.sha256(f"{HOTE_GRIST}/{document}/{reference}".encode()).hexdigest()
    return f"grist-{empreinte}"


def edition_grist(url, reference, numero):
    catalogue, lignes = lire_catalogue_grist(url, avec_lignes=True)
    source = next((ligne for ligne in catalogue["referentiels"] if ligne["reference"] == reference), None)
    if not source or numero not in source["editions"]:
        raise ValidationError("Cette édition ne figure plus dans le catalogue Grist.")
    prefixe, document = adresse_grist(catalogue["url"])
    for ligne in lignes:
        if ligne.get("Numero") == numero and ligne.get("Referentiel") == reference and ligne.get("Contenu"):
            contenu = texte(ligne["Contenu"], "Contenu de l’édition", TAILLE_MAX)
            try:
                edition = json.loads(contenu)
                if not isinstance(edition, dict) or not isinstance(edition.get("source"), dict):
                    raise ValueError
                edition["source"]["identifiant"] = identite_grist(catalogue["url"], reference)
                edition["source"]["titre"] = source["titre"]
                edition["version"] = str(numero)
            except ValueError as erreur:
                raise ValidationError("Le contenu de l’édition Grist est illisible.") from erreur
            return yaml.safe_dump(edition, allow_unicode=True)
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
