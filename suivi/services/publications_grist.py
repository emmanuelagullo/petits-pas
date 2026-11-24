"""Publication d’une édition entière dans une ligne Grist."""
import json

from django.core.exceptions import ValidationError

from .catalogues_externes import (
    TAILLE_MAX, adresse_grist, document_grist, lignes_grist, lire_api,
    nom_catalogue_grist, numerotation_grist_globale, referentiels_grist, requete_api,
)

CHEMIN_EDITIONS = "/tables/Editions/records"
COLONNES = {"Numero": {"Int", "Numeric"}, **{
    nom: {"Text"} for nom in ("Referentiel", "Titre", "Contenu")
}}


def editions_grist(prefixe, document):
    return lignes_grist(lire_api(prefixe, document, CHEMIN_EDITIONS))


def destination_grist(url, *, preparer_vierge=False):
    prefixe, document, url, nom = document_grist(url)
    try:
        tables = lire_api(prefixe, document, "/tables")
        noms = {table["id"] for table in tables["tables"]}
        if "Editions" not in noms:
            if not preparer_vierge or not document_vierge(prefixe, document, noms):
                raise ValidationError("Ce document ne contient pas de table Editions compatible. "
                                      "Choisissez un document Grist vierge ou un catalogue Petits Pas.")
            creer_table_editions(prefixe, document)
        colonnes = {c["id"]: c["fields"]["type"]
                    for c in lire_api(prefixe, document, "/tables/Editions/columns")["columns"]}
    except (KeyError, TypeError) as erreur:
        raise ValidationError("Le schéma du document Grist est illisible.") from erreur
    manquantes = [nom for nom, types in COLONNES.items() if colonnes.get(nom) not in types]
    if manquantes:
        raise ValidationError("Publication impossible : la table Editions a des colonnes manquantes ou de type incorrect (%(colonnes)s).",
                              params={"colonnes": ", ".join(manquantes)})
    editions = editions_grist(prefixe, document)
    referentiels_grist(editions)
    nom_partage = nom_catalogue_grist(prefixe, document, noms)
    return {"url": url, "nom": nom_partage or nom, "nom_a_initialiser": not nom_partage and not editions,
            "espace": prefixe.removeprefix("/o/"), "editions": editions}


def document_vierge(prefixe, document, tables):
    return not tables or (
        tables == {"Table1"}
        and not lignes_grist(lire_api(prefixe, document, "/tables/Table1/records?limit=1"))
    )


def creer_table_editions(prefixe, document):
    colonnes = [{"id": nom, "fields": {"type": "Int" if nom == "Numero" else "Text"}} for nom in COLONNES]
    corps = json.dumps({"tables": [{"id": "Editions", "columns": colonnes}]}).encode()
    try:
        requete_api(prefixe, document, "/tables", corps=corps, methode="POST")
    except ValidationError:
        # Un autre envoi a pu créer la table entre-temps. Le schéma sera vérifié ensuite.
        if "Editions" not in {table["id"] for table in lire_api(prefixe, document, "/tables")["tables"]}:
            raise


def meme_contenu_grist(edition, document):
    try:
        ancien = json.loads(edition.get("Contenu") or "")
    except (TypeError, ValueError):
        return False
    if not isinstance(ancien, dict):
        return False
    actuel = json.loads(contenu_grist(document))
    ancien.pop("version", None)
    actuel.pop("version", None)
    return ancien == actuel


def contenu_grist(document):
    return json.dumps({cle: valeur for cle, valeur in document.items() if cle != "origine"},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def publier_edition_grist(destination, reference, titre, numero, document):
    prefixe, identifiant = adresse_grist(destination["url"])
    contenu = contenu_grist(document)
    champs = {"Referentiel": reference, "Titre": titre, "Contenu": contenu}
    globale = numerotation_grist_globale(destination.get("editions", ()))
    cle = {"Numero": numero}
    if not globale:
        cle["Referentiel"] = reference
    corps = json.dumps({"records": [{"require": cle, "fields": champs}]},
                       ensure_ascii=False).encode()
    if len(corps) > TAILLE_MAX:
        raise ValidationError("Cette édition est trop volumineuse pour la publication Grist. Téléchargez le ZIP.")

    def correspond(ligne):
        return all(ligne.get(nom) == valeur for nom, valeur in cle.items())

    try:
        requete_api(prefixe, identifiant, f"{CHEMIN_EDITIONS}?noparse=true&noupdate=true&onmany=none", corps=corps)
    except ValidationError as erreur:
        # Une réponse peut se perdre après l’écriture. Seule une relecture
        # identique permet de conclure que la publication est réussie.
        try:
            editions = editions_grist(prefixe, identifiant)
        except ValidationError:
            raise erreur
        if not any(correspond(ligne) for ligne in editions):
            raise erreur
    else:
        editions = editions_grist(prefixe, identifiant)
    correspondantes = [ligne for ligne in editions if correspond(ligne)]
    if len(correspondantes) != 1 or any(correspondantes[0].get(cle) != valeur for cle, valeur in champs.items()):
        raise ValidationError("Ce numéro est déjà utilisé ou l’écriture n’a pas été confirmée. Examinez de nouveau la destination.")
