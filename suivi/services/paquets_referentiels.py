"""Archives de diffusion du catalogue, distinctes des sauvegardes d’école."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import re
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

import yaml
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence
from suivi.icones_partagees import MAX_PNG, PREFIXE, decoder_icone, empreinte_png, encoder_icone, externaliser_png, png_en_ligne
from suivi.presentation import catalogue_icones
from .import_sources_referentiels import ChargeurSansDoublons, lire_source

MAX_ARCHIVE = 16 * 1024 * 1024
DOCUMENT = "referentiel.yaml"


def ressources(contenu):
    fichiers = {}
    icones = catalogue_icones()
    for cle in sorted({c["icone"] for c in competences_document(contenu) if c["icone"]}):
        notice = icones[cle]
        chemin = finders.find(notice["fichier"])
        if not chemin:
            raise ValidationError(f"Fichier de l’icône introuvable : {cle}.")
        with open(chemin, "rb") as fichier:
            fichiers[f"icones/{cle}.svg"] = fichier.read(MAX_ARCHIVE + 1)
    if fichiers:
        fichiers["credits.yaml"] = yaml.safe_dump(
            {cle: icones[cle] for cle in sorted(icones) if f"icones/{cle}.svg" in fichiers},
            allow_unicode=True,
        ).encode()
    return fichiers


def exporter_paquet(version):
    document = dict(version.contenu)
    if document.pop("origine", None) != "source_declaree":
        raise ValidationError("Choisissez une édition publique du catalogue.")
    return empaqueter(document)


def exporter_selection(version, references):
    document = deepcopy(version.contenu)
    if document.pop("origine", None) != "source_declaree":
        raise ValidationError("Choisissez une édition publique du catalogue.")
    references = set(references)
    disponibles = {reference_competence(c) for c in competences_document(document)}
    if not references or not references <= disponibles:
        raise ValidationError("Choisissez les compétences à exporter.")
    for domaine in document["domaines"]:
        groupes = [domaine, *domaine["sous_domaines"]]
        for groupe in groupes:
            groupe["competences"] = [c for c in groupe["competences"] if reference_competence(c) in references]
            for c in groupe["competences"]:
                c.setdefault("source_origine", version.contenu["source"]["identifiant"])
        domaine["sous_domaines"] = [s for s in domaine["sous_domaines"] if s["competences"]]
    document["domaines"] = [d for d in document["domaines"] if d["competences"] or d["sous_domaines"]]
    empreinte = sha256(yaml.safe_dump(document, allow_unicode=True).encode()).hexdigest()
    document["format"] = 2
    document["version"] = "1"
    document["source"]["identifiant"] = f"selection-{empreinte}"
    document["source"]["titre"] = f"Sélection · {document['source']['titre']}"[:200]
    return empaqueter(document)


def exporter_ajout(locale, definition, *, provenance, licence, icone="", formulations=(), image=None):
    if locale.suivi_libre:
        raise ValidationError("Une compétence de suivi ciblé ne peut pas être partagée.")
    origine = locale.definition["competences"][0]
    identifiant = locale.definition.get("identite_portable") or origine["code"]
    competence = {"identite": identifiant, "code": "C1", "libelle": definition["libelle"],
                  "niveau": definition["niveau"], "icone": icone, "formulations": list(formulations)}
    if locale.definition.get("variante_de"):
        competence["variante_de"] = locale.definition["variante_de"]
    if image is not None:
        competence["icone_png"] = encoder_icone(image)
    # La même fiche pédagogique produit la même édition sur un autre poste.
    empreinte = sha256(yaml.safe_dump(competence, allow_unicode=True).encode()).hexdigest()
    return empaqueter({
        "format": 2, "version": empreinte,
        "source": {"identifiant": f"ajout-{identifiant}", "titre": "Compétence partagée",
                   "provenance": provenance, "licence": licence, "provisoire": True},
        "domaines": [{"code": "partage", "nom": "Compétence partagée", "competences": [competence]}],
    })


def empaqueter(document):
    portable = deepcopy(document)
    for c in competences_document(portable):
        if c.get("icone_png"):
            c["icone_png"] = png_en_ligne(c["icone_png"])
    normalise, _ = lire_source(yaml.safe_dump(portable, allow_unicode=True))
    fichiers = ressources(normalise)
    fichiers.update({f"icones/{empreinte}.png": donnees
                     for empreinte, donnees in externaliser_png(portable).items()})
    fichiers[DOCUMENT] = yaml.safe_dump(portable, allow_unicode=True).encode()
    if sum(map(len, fichiers.values())) > MAX_ARCHIVE:
        raise ValidationError("Le référentiel dépasse la taille maximale du paquet.")
    sortie = BytesIO()
    with ZipFile(sortie, "w", compression=ZIP_DEFLATED) as archive:
        for nom, donnees in fichiers.items():
            archive.writestr(nom, donnees)
    return sortie.getvalue()


def lire_paquet(donnees):
    if len(donnees) > MAX_ARCHIVE:
        raise ValidationError("Le référentiel dépasse la taille maximale du paquet.")
    try:
        with ZipFile(BytesIO(donnees)) as archive:
            membres = archive.infolist()
            noms = {m.filename for m in membres}
            if len(noms) != len(membres) or DOCUMENT not in noms or sum(m.file_size for m in membres) > MAX_ARCHIVE:
                raise ValidationError("Paquet de référentiel invalide.")
            texte = archive.read(DOCUMENT).decode("utf-8")
            document = yaml.load(texte, Loader=ChargeurSansDoublons)
            png = {}
            if isinstance(document, dict):
                def restaurer(objet):
                    if isinstance(objet, dict):
                        valeur = objet.get("icone_png")
                        if isinstance(valeur, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", valeur):
                            empreinte = valeur[len(PREFIXE):]
                            nom = f"icones/{empreinte}.png"
                            if nom not in noms or archive.getinfo(nom).file_size > MAX_PNG:
                                raise ValidationError("Une icône PNG du paquet est absente ou trop grande.")
                            if nom not in png:
                                donnees_png = archive.read(nom)
                                if empreinte_png(donnees_png) != empreinte:
                                    raise ValidationError("L’empreinte d’une icône PNG ne correspond pas.")
                                png[nom] = donnees_png
                            objet["icone_png"] = encoder_icone(png[nom])
                        for valeur in objet.values():
                            restaurer(valeur)
                    elif isinstance(objet, list):
                        for valeur in objet:
                            restaurer(valeur)

                restaurer(document)
            texte = yaml.safe_dump(document, allow_unicode=True)
            normalise, _ = lire_source(texte)
            attendus = {**ressources(normalise), **png}
            if noms != {DOCUMENT, *attendus} or any(archive.read(nom) != valeur for nom, valeur in attendus.items()):
                raise ValidationError("Les icônes ou les crédits du paquet diffèrent du catalogue fourni.")
            return texte
    except (BadZipFile, RuntimeError, NotImplementedError, UnicodeError, yaml.YAMLError) as erreur:
        raise ValidationError("Paquet de référentiel illisible.") from erreur
