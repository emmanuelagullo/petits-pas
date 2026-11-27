"""Lecture du format de catalogue Grist utilisé dans le pilote."""
import hashlib
import json
import re
from uuid import UUID
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
from django.core.exceptions import ValidationError

from .import_sources_referentiels import identifiant, texte

HOTE_GRIST = "grist.numerique.gouv.fr"
CATALOGUE_DEMONSTRATION = f"https://{HOTE_GRIST}/o/docs/sq1Lck5R9KFj"
TAILLE_MAX = 1024 * 1024


CATALOGUES_FOURNIS = {
    CATALOGUE_DEMONSTRATION: {
        "url": CATALOGUE_DEMONSTRATION,
        "lien": CATALOGUE_DEMONSTRATION + "/petits-pas-essayer",
        "nom": "Petits Pas – Catalogue d’essai",
        "essai": True,
        "referentiels": [
            {"reference": f"grist-recette-demo-{index}", "titre": f"Référentiel des {classe}", "editions": [1]}
            for index, classe in enumerate(("Mésanges", "Hirondelles", "Chardonnerets"), 1)
        ],
    },
}


def partage_grist_disponible():
    from django.conf import settings

    return settings.MODE_LOCAL or getattr(settings, "MODE_PWA", False) or settings.GRIST_PARTAGE_SERVEUR


def catalogues_grist_connus(reglages):
    from django.conf import settings

    return {**(CATALOGUES_FOURNIS if settings.ESPACE_ESSAI else {}),
            **{cle: etat["catalogue"] for cle, etat in reglages.items() if "catalogue" in etat}}


def reglages_catalogues_classe(classe):
    regles = {cle: dict(etat) for cle, etat in classe.ecole.catalogues_referentiels.items()}
    for cle, etat in classe.catalogues_propres.items():
        regles.setdefault(cle, {}).update(etat)
    return regles


def adresse_grist(valeur):
    try:
        adresse = urlsplit(valeur.strip())
    except ValueError as erreur:
        raise ValidationError("Le lien Grist est invalide.") from erreur
    chemin = re.fullmatch(r"(/o/([A-Za-z0-9_-]+))?/([A-Za-z0-9_-]{8,64})(?:/[^/]+)?(?:/p/[A-Za-z0-9_-]+)?/?", adresse.path)
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
        if reference_classe_grist(cle):
            raise ValidationError("Cette référence est réservée aux référentiels courants des classes.")
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
        contenu = ligne.get("Contenu")
        try:
            origine = json.loads(contenu).get("origine_classe_grist") if contenu else None
        except (AttributeError, TypeError, ValueError):
            origine = None
        if reference_classe_grist(origine):
            source.setdefault("origines", {})[numero] = origine
        source["editions"].append(numero)
    for source in referentiels.values():
        source["editions"].sort(reverse=True)
        origines = source.pop("origines", {})
        if source["editions"][0] in origines:
            source["origine_classe_grist"] = origines[source["editions"][0]]
    return list(referentiels.values())


TABLE_NOMS_GRIST = "PetitsPasEspace"
NOMS_GRIST = f"/tables/{TABLE_NOMS_GRIST}/records"


def tables_grist(prefixe, document):
    try:
        return {table["id"] for table in lire_api(prefixe, document, "/tables")["tables"]}
    except (KeyError, TypeError) as erreur:
        raise ValidationError("Le schéma du document Grist est illisible.") from erreur


MODES_CATALOGUE_GRIST = {
    "competences": "Compétences",
    "complet": "Compétences et icônes",
    "icones": "Icônes seules",
}


def mode_catalogue_grist(prefixe, document, tables):
    if TABLE_NOMS_GRIST not in tables:
        return "complet"
    lignes = lignes_grist(lire_api(prefixe, document, NOMS_GRIST))
    modes = [ligne.get("Nom") for ligne in lignes if ligne.get("Identifiant") == "mode-contenu"]
    if not modes:
        return "complet"
    if len(modes) != 1 or not isinstance(modes[0], str) or modes[0] not in MODES_CATALOGUE_GRIST:
        raise ValidationError("Le mode de contenu du catalogue Grist est invalide.")
    return modes[0]


def preparer_metadonnees_grist(prefixe, document, tables):
    if TABLE_NOMS_GRIST not in tables:
        colonnes = [{"id": cle, "fields": {"type": "Text"}} for cle in ("Identifiant", "Nom")]
        corps = json.dumps({"tables": [{"id": TABLE_NOMS_GRIST, "columns": colonnes}]}).encode()
        try:
            requete_api(prefixe, document, "/tables", corps=corps, methode="POST")
        except ValidationError:
            if TABLE_NOMS_GRIST not in tables_grist(prefixe, document):
                raise


def enregistrer_mode_catalogue_grist(url, mode):
    if mode not in MODES_CATALOGUE_GRIST:
        raise ValidationError("Choisissez les contenus du catalogue.")
    prefixe, document = adresse_grist(url)
    preparer_metadonnees_grist(prefixe, document, tables_grist(prefixe, document))
    corps = json.dumps({"records": [{"require": {"Identifiant": "mode-contenu"},
                                      "fields": {"Nom": mode}}]}).encode()
    requete_api(prefixe, document, NOMS_GRIST + "?noparse=true&onmany=none", corps=corps)
    if mode_catalogue_grist(prefixe, document, {TABLE_NOMS_GRIST}) != mode:
        raise ValidationError("Le changement de contenu du catalogue n’a pas été confirmé.")


def nom_catalogue_grist(prefixe, document, tables):
    if TABLE_NOMS_GRIST not in tables:
        return ""
    lignes = lignes_grist(lire_api(prefixe, document, NOMS_GRIST))
    noms = [ligne.get("Nom") for ligne in lignes if ligne.get("Identifiant") == "catalogue"]
    if len(noms) > 1:
        raise ValidationError("Plusieurs noms sont enregistrés pour ce catalogue.")
    return texte(noms[0], "Nom du catalogue") if noms else ""


def enregistrer_nom_catalogue_grist(url, nom, *, remplacer=False):
    prefixe, document = adresse_grist(url)
    nom = texte(nom.strip(), "Nom du catalogue")
    tables = tables_grist(prefixe, document)
    if "Editions" not in tables:
        raise ValidationError("Ce document ne contient pas de catalogue Petits Pas.")
    preparer_metadonnees_grist(prefixe, document, tables)
    corps = json.dumps({"records": [{"require": {"Identifiant": "catalogue"},
                                     "fields": {"Nom": nom}}]}, ensure_ascii=False).encode()
    options = "?noparse=true&onmany=none" + ("" if remplacer else "&noupdate=true")
    requete_api(prefixe, document, NOMS_GRIST + options, corps=corps)
    return nom_catalogue_grist(prefixe, document, {TABLE_NOMS_GRIST})


def lire_catalogue_grist(url, *, avec_lignes=False):
    prefixe, document, url, nom = document_grist(url)
    tables = tables_grist(prefixe, document)
    espace = {"PetitsPasClasses", "PetitsPasContenus"} <= tables
    lignes = (lignes_grist(lire_api(prefixe, document, "/tables/Editions/records"))
              if "Editions" in tables or not espace else [])
    referentiels = referentiels_grist(lignes)
    mode = mode_catalogue_grist(prefixe, document, tables)
    if espace and mode != "icones":
        for ligne in lignes_grist(lire_api(prefixe, document, "/tables/PetitsPasClasses/records")):
            try:
                reference = "classe-grist-" + str(UUID(ligne["Identifiant"]))
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            empreinte = ligne.get("Empreinte")
            titre = ligne.get("Nom")
            if isinstance(empreinte, str) and re.fullmatch(r"[0-9a-f]{64}", empreinte) and isinstance(titre, str) and titre:
                referentiels.append({"reference": reference, "titre": titre[:200],
                                     "editions": [empreinte], "contenu_courant": True})
    if not referentiels and mode != "icones" and not espace:
        raise ValidationError("Ce catalogue Grist ne contient aucune édition.")
    nom_partage = nom_catalogue_grist(prefixe, document, tables)
    resultat = {"url": url, "nom": nom_partage or nom,
                "referentiels": [] if mode == "icones" else referentiels,
                "mode_contenu": mode, "libelle_contenu": MODES_CATALOGUE_GRIST[mode]}
    return (resultat, lignes) if avec_lignes else resultat


def reference_classe_grist(reference):
    return isinstance(reference, str) and bool(re.fullmatch(
        r"classe-grist-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", reference,
    ))


def identite_grist(url, reference):
    if reference_classe_grist(reference):
        return reference
    _, document = adresse_grist(url)
    empreinte = hashlib.sha256(f"{HOTE_GRIST}/{document}/{reference}".encode()).hexdigest()
    return f"grist-{empreinte}"


TABLE_ICONES_GRIST = "PetitsPasIcones"
CHEMIN_ICONES_GRIST = f"/tables/{TABLE_ICONES_GRIST}/records"


def lire_icone_grist(prefixe, document, empreinte, *, facultative=False):
    from urllib.parse import urlencode

    from suivi.icones_partagees import decoder_icone, empreinte_png

    filtre = urlencode({"filter": json.dumps({"Empreinte": [empreinte]})})
    lignes = lignes_grist(lire_api(prefixe, document, f"{CHEMIN_ICONES_GRIST}?{filtre}"))
    if not lignes and facultative:
        return None
    if len(lignes) != 1 or lignes[0].get("Empreinte") != empreinte:
        raise ValidationError(f"Icône {empreinte[:12]} absente du catalogue Grist.")
    donnees = decoder_icone(lignes[0].get("PNG"))
    if empreinte_png(donnees) != empreinte:
        raise ValidationError(f"Icône {empreinte[:12]} altérée dans le catalogue Grist.")
    return donnees


def icones_catalogue_grist(url):
    from suivi.icones_partagees import decoder_icone, empreinte_png

    prefixe, document = adresse_grist(url)
    tables = tables_grist(prefixe, document)
    if mode_catalogue_grist(prefixe, document, tables) == "competences":
        raise ValidationError("Ce catalogue ne propose actuellement que les compétences.")
    if TABLE_ICONES_GRIST not in tables:
        raise ValidationError("Ce catalogue ne contient aucune icône ajoutée.")
    ressources = {}
    for ligne in lignes_grist(lire_api(prefixe, document, CHEMIN_ICONES_GRIST)):
        png = decoder_icone(ligne.get("PNG"))
        cle = empreinte_png(png)
        if ligne.get("Empreinte") != cle or cle in ressources:
            raise ValidationError("Une icône du catalogue est altérée ou en double.")
        ressources[cle] = png
    return ressources


def restituer_icones_grist(edition, prefixe, document):
    from suivi.icones_partagees import PREFIXE, png_en_ligne
    from suivi.identites_referentiels import competences_document
    from base64 import b64encode

    ressources = {}
    for competence in competences_document(edition):
        valeur = competence.get("icone_png")
        if not isinstance(valeur, str) or not valeur.startswith(PREFIXE):
            continue
        empreinte = valeur[len(PREFIXE):]
        if not re.fullmatch(r"[0-9a-f]{64}", empreinte):
            raise ValidationError("Empreinte d’icône invalide.")
        if empreinte not in ressources:
            try:
                ressources[empreinte] = png_en_ligne(valeur)
            except ValidationError:
                donnees = lire_icone_grist(prefixe, document, empreinte)
                ressources[empreinte] = b64encode(donnees).decode("ascii")
        competence["icone_png"] = ressources[empreinte]


def edition_grist(url, reference, numero, *, avec_catalogue=False):
    catalogue, lignes = lire_catalogue_grist(url, avec_lignes=True)
    source = next((ligne for ligne in catalogue["referentiels"] if ligne["reference"] == reference), None)
    if not source or numero not in source["editions"]:
        raise ValidationError("Cette édition ne figure plus dans le catalogue Grist.")
    prefixe, document = adresse_grist(catalogue["url"])
    if source.get("contenu_courant"):
        from urllib.parse import urlencode

        filtre = urlencode({"filter": json.dumps({"Identifiant": [reference.removeprefix("classe-grist-")]})})
        recues = lignes_grist(lire_api(prefixe, document, "/tables/PetitsPasContenus/records?" + filtre))
        if len(recues) != 1 or recues[0].get("Identifiant") != reference.removeprefix("classe-grist-"):
            raise ValidationError("Le référentiel courant est indisponible.")
        brut = texte(recues[0].get("Contenu"), "Référentiel courant", TAILLE_MAX)
        if hashlib.sha256(brut.encode()).hexdigest() != numero:
            raise ValidationError("Le référentiel courant a changé. Actualisez le catalogue.")
        try:
            edition = json.loads(brut)
            licence = edition["source"]["licence"]
            titre = edition["source"]["titre"]
        except (TypeError, ValueError, KeyError) as erreur:
            raise ValidationError("Le référentiel courant est illisible.") from erreur
        edition["source"] = {"identifiant": reference, "titre": titre,
                            "provenance": "Espace de partage Petits Pas", "licence": licence, "provisoire": True}
        edition["version"] = numero
        restituer_icones_grist(edition, prefixe, document)
        resultat = yaml.safe_dump(edition, allow_unicode=True)
        return (resultat, catalogue) if avec_catalogue else resultat
    for ligne in lignes:
        if ligne.get("Numero") == numero and ligne.get("Referentiel") == reference and ligne.get("Contenu"):
            contenu = texte(ligne["Contenu"], "Contenu de l’édition", TAILLE_MAX)
            try:
                edition = json.loads(contenu)
                if not isinstance(edition, dict) or not isinstance(edition.get("source"), dict):
                    raise ValueError
                edition.pop("origine_classe_grist", None)
                edition["source"]["identifiant"] = identite_grist(catalogue["url"], reference)
                edition["source"]["titre"] = source["titre"]
                edition["version"] = str(numero)
            except ValueError as erreur:
                raise ValidationError("Le contenu de l’édition Grist est illisible.") from erreur
            restituer_icones_grist(edition, prefixe, document)
            resultat = yaml.safe_dump(edition, allow_unicode=True)
            return (resultat, catalogue) if avec_catalogue else resultat
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
    resultat = yaml.safe_dump({
        "format": 1, "version": str(numero),
        "source": {"identifiant": identite_grist(catalogue["url"], reference), "titre": source["titre"],
                   "provenance": f"Document Grist {HOTE_GRIST}/{document}",
                   "licence": "Non renseignée", "provisoire": True},
        "domaines": list(domaines.values()),
    }, allow_unicode=True)
    return (resultat, catalogue) if avec_catalogue else resultat


def suggestions_catalogues_grist(utilisateur, ecole, classe=None, *, prioritaires=()):
    """Lister par document les adresses connues du périmètre ou de l’utilisateur."""
    from suivi.models import DestinationPublicationGrist, PartageGristClasse

    reglages = reglages_catalogues_classe(classe) if classe else ecole.catalogues_referentiels
    propositions = list(prioritaires)
    if classe:
        partage = PartageGristClasse.objects.filter(classe=classe).first()
        if partage:
            propositions.append({"url": partage.url, "nom": partage.nom_espace or "Espace de partage"})
    propositions.extend(catalogues_grist_connus(reglages).values())
    propositions.extend(DestinationPublicationGrist.objects.filter(ecole=ecole, auteur=utilisateur)
                        .order_by("-publie_le", "-pk").values("url", "nom", "espace"))
    documents = {}
    for proposition in propositions:
        if not proposition.get("url"):
            continue
        try:
            _, document = adresse_grist(proposition["url"])
        except ValidationError:
            continue
        documents.setdefault(document, proposition)
    return list(documents.values())
