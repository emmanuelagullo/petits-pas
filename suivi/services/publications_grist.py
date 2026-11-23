"""Publication d’une édition entière dans une ligne Grist."""
import json

from django.core.exceptions import ValidationError

from .catalogues_externes import TAILLE_MAX, adresse_grist, document_grist, lignes_grist, lire_api, requete_api

CHEMIN_EDITIONS = "/tables/Editions/records"
COLONNES = {"Numero": {"Int", "Numeric"}, **{
    nom: {"Text"} for nom in ("Referentiel", "Titre", "Contenu")
}}


def editions_grist(prefixe, document):
    return lignes_grist(lire_api(prefixe, document, CHEMIN_EDITIONS))


def destination_grist(url):
    prefixe, document, url, nom = document_grist(url)
    try:
        tables = lire_api(prefixe, document, "/tables")
        if "Editions" not in {table["id"] for table in tables["tables"]}:
            raise ValidationError("Ce document ne contient pas la table Editions du modèle Petits Pas.")
        colonnes = {c["id"]: c["fields"]["type"]
                    for c in lire_api(prefixe, document, "/tables/Editions/columns")["columns"]}
    except (KeyError, TypeError) as erreur:
        raise ValidationError("Le schéma du document Grist est illisible.") from erreur
    manquantes = [nom for nom, types in COLONNES.items() if colonnes.get(nom) not in types]
    if manquantes:
        raise ValidationError("Vérifiez les colonnes de la table Editions : %(colonnes)s.",
                              params={"colonnes": ", ".join(manquantes)})
    editions = editions_grist(prefixe, document)
    numeros = [ligne.get("Numero") for ligne in editions]
    if any(type(n) is not int or n < 1 for n in numeros) or len(numeros) != len(set(numeros)):
        raise ValidationError("Les numéros de la table Editions doivent être des entiers positifs distincts.")
    references = {}
    for ligne in editions:
        reference = ligne.get("Referentiel")
        titre = ligne.get("Titre")
        if not isinstance(reference, str) or not reference or not isinstance(titre, str) or not titre:
            raise ValidationError("Vérifiez les titres et identifiants de la table Editions.")
        if references.setdefault(reference, titre) != titre:
            raise ValidationError("Un référentiel a plusieurs titres dans la table Editions.")
    return {"url": url, "nom": nom, "espace": prefixe.removeprefix("/o/"), "editions": editions}


def publier_edition_grist(destination, reference, titre, numero, document):
    prefixe, identifiant = adresse_grist(destination["url"])
    contenu = json.dumps({cle: valeur for cle, valeur in document.items() if cle != "origine"},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    champs = {"Referentiel": reference, "Titre": titre, "Contenu": contenu}
    corps = json.dumps({"records": [{"require": {"Numero": numero}, "fields": champs}]},
                       ensure_ascii=False).encode()
    if len(corps) > TAILLE_MAX:
        raise ValidationError("Cette édition est trop volumineuse pour la publication Grist. Téléchargez le ZIP.")
    try:
        requete_api(prefixe, identifiant, f"{CHEMIN_EDITIONS}?noparse=true&noupdate=true&onmany=none", corps=corps)
    except ValidationError as erreur:
        # Une réponse peut se perdre après l’écriture. Seule une relecture
        # identique permet de conclure que la publication est réussie.
        try:
            editions = editions_grist(prefixe, identifiant)
        except ValidationError:
            raise erreur
        if not any(ligne.get("Numero") == numero for ligne in editions):
            raise erreur
    else:
        editions = editions_grist(prefixe, identifiant)
    correspondantes = [ligne for ligne in editions if ligne.get("Numero") == numero]
    if len(correspondantes) != 1 or any(correspondantes[0].get(cle) != valeur for cle, valeur in champs.items()):
        raise ValidationError("Ce numéro est déjà utilisé ou l’écriture n’a pas été confirmée. Examinez de nouveau la destination.")
