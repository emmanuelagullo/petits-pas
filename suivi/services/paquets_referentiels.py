"""Archives de diffusion du catalogue, distinctes des sauvegardes d’école."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

import yaml
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document, reference_competence
from suivi.presentation import catalogue_icones
from .import_sources_referentiels import lire_source

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


def empaqueter(document):
    document_yaml = yaml.safe_dump(document, allow_unicode=True).encode()
    normalise, _ = lire_source(document_yaml)
    fichiers = {DOCUMENT: document_yaml, **ressources(normalise)}
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
            normalise, _ = lire_source(texte)
            attendus = ressources(normalise)
            if noms != {DOCUMENT, *attendus} or any(archive.read(nom) != valeur for nom, valeur in attendus.items()):
                raise ValidationError("Les icônes ou les crédits du paquet diffèrent du catalogue fourni.")
            return texte
    except (BadZipFile, RuntimeError, NotImplementedError, UnicodeError) as erreur:
        raise ValidationError("Paquet de référentiel illisible.") from erreur
