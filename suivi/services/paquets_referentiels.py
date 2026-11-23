"""Archives de diffusion du catalogue, distinctes des sauvegardes d’école."""
from io import BytesIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

import yaml
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError

from suivi.identites_referentiels import competences_document
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
    if version.source.ecole_id is not None or document.pop("origine", None) != "source_declaree":
        raise ValidationError("Choisissez une édition publique du catalogue.")
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
