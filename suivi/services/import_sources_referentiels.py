"""Import au catalogue : aucune adoption ni écriture dans le suivi des élèves."""
import hashlib
import json
import re

import yaml
from django.core.exceptions import ValidationError
from django.db import transaction

from suivi.models import (DefinitionSourceCompetence, IdentiteSourceCompetence,
                          SourceReferentiel, VersionReferentiel)
from suivi.presentation import catalogue_icones


class ChargeurSansDoublons(yaml.SafeLoader):
    """Une clé YAML répétée ne doit pas remplacer une donnée silencieusement."""


def dictionnaire(loader, node, deep=False):
    resultat = {}
    for cle_node, valeur_node in node.value:
        cle = loader.construct_object(cle_node, deep=deep)
        if not isinstance(cle, str) or cle in resultat:
            raise ValidationError("Une clé YAML est répétée ou n'est pas un texte.")
        resultat[cle] = loader.construct_object(valeur_node, deep=deep)
    return resultat


ChargeurSansDoublons.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dictionnaire)


def objet(valeur, champs, chemin):
    if not isinstance(valeur, dict) or set(valeur) - set(champs):
        raise ValidationError(f"{chemin} : objet attendu, avec uniquement les champs {', '.join(champs)}.")
    return valeur


def texte(valeur, chemin, maximum=200, facultatif=False):
    if not isinstance(valeur, str) or len(valeur) > maximum or (not facultatif and not valeur.strip()):
        raise ValidationError(f"{chemin} : texte {'facultatif' if facultatif else 'non vide'} attendu (maximum {maximum} caractères).")
    return valeur


def identifiant(valeur, chemin, maximum=120):
    valeur = texte(valeur, chemin, maximum)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", valeur):
        raise ValidationError(f"{chemin} : utiliser lettres sans accents, chiffres, points, tirets ou soulignements.")
    return valeur


def liste(valeur, chemin):
    if not isinstance(valeur, list):
        raise ValidationError(f"{chemin} : liste attendue.")
    return valeur


def normaliser(document):
    document = objet(document, ("format", "source", "version", "domaines"), "Document")
    if type(document.get("format")) is not int or document["format"] != 1:
        raise ValidationError("Format attendu : 1.")
    source = objet(document.get("source"), ("identifiant", "titre", "provenance", "licence", "provisoire"), "Source")
    source = {"identifiant": identifiant(source.get("identifiant"), "Identifiant de source"),
              "titre": texte(source.get("titre"), "Titre"),
              "provenance": texte(source.get("provenance"), "Provenance", 4000),
              "licence": texte(source.get("licence"), "Licence", 120),
              "provisoire": source.get("provisoire")}
    if source["identifiant"].startswith("reprise-ecole-"):
        raise ValidationError("Cet identifiant est réservé aux reprises de bases existantes.")
    if type(source["provisoire"]) is not bool:
        raise ValidationError("Provisoire doit valoir true ou false.")
    numero = identifiant(document.get("version"), "Version", 80)
    domaines = []
    identites, codes_competences, codes_domaines = set(), set(), set()

    def unique(valeur, ensemble, chemin):
        if valeur in ensemble:
            raise ValidationError(f"{chemin} répété : {valeur}.")
        ensemble.add(valeur)
        return valeur

    def competences(valeurs, chemin):
        resultat = []
        for c in liste(valeurs, chemin):
            c = objet(c, ("identite", "code", "libelle", "niveau", "icone", "formulations"), "Compétence")
            identite = unique(identifiant(c.get("identite"), "Identité"), identites, "Identité")
            code = unique(identifiant(c.get("code"), "Code de compétence", 20), codes_competences, "Code de compétence")
            niveau = c.get("niveau", "PS")
            if niveau not in ("PS", "MS", "GS"):
                raise ValidationError("Niveau attendu : PS, MS ou GS.")
            icone = texte(c.get("icone", ""), "Icône", 120, facultatif=True)
            if icone and icone not in catalogue_icones():
                raise ValidationError(f"Icône inconnue : {icone}.")
            formulations, codes_phrases = [], set()
            for f in liste(c.get("formulations", []), "Phrases proposées"):
                f = objet(f, ("code", "texte"), "Phrase proposée")
                formulations.append({"code": unique(identifiant(f.get("code"), "Code de phrase", 80), codes_phrases, "Code de phrase"),
                                     "texte": texte(f.get("texte"), "Phrase proposée", 4000)})
            resultat.append({"identite": identite, "code": code, "libelle": texte(c.get("libelle"), "Libellé", 300),
                             "niveau": niveau, "icone": icone, "formulations": formulations})
        return resultat

    for d in liste(document.get("domaines"), "Domaines"):
        d = objet(d, ("code", "nom", "attendus", "competences", "sous_domaines"), "Domaine")
        domaine = {"code": unique(identifiant(d.get("code"), "Code de domaine", 20), codes_domaines, "Code de domaine"),
                   "nom": texte(d.get("nom"), "Nom de domaine"),
                   "competences": competences(d.get("competences", []), "Compétences"),
                   "attendus": [], "sous_domaines": []}
        codes_attendus, codes_sous_domaines = set(), set()
        for a in liste(d.get("attendus", []), "Attendus"):
            a = objet(a, ("code", "texte"), "Attendu")
            domaine["attendus"].append({"code": unique(identifiant(a.get("code"), "Code d'attendu", 20), codes_attendus, "Code d'attendu"),
                                        "texte": texte(a.get("texte"), "Texte d'attendu", 4000)})
        for s in liste(d.get("sous_domaines", []), "Sous-domaines"):
            s = objet(s, ("code", "nom", "competences"), "Sous-domaine")
            domaine["sous_domaines"].append({"code": unique(identifiant(s.get("code"), "Code de sous-domaine", 20), codes_sous_domaines, "Code de sous-domaine"),
                                            "nom": texte(s.get("nom"), "Nom de sous-domaine"),
                                            "competences": competences(s.get("competences", []), "Compétences du sous-domaine")})
        domaines.append(domaine)
    if not domaines or not identites:
        raise ValidationError("Au moins un domaine et une compétence sont nécessaires.")
    return {"format": 1, "origine": "source_declaree", "source": source, "version": numero, "domaines": domaines}, identites


def lire_source(contenu_yaml):
    try:
        document = yaml.load(contenu_yaml, Loader=ChargeurSansDoublons)
    except yaml.YAMLError as erreur:
        raise ValidationError("Le fichier YAML est invalide.") from erreur
    return normaliser(document)


@transaction.atomic
def importer_source(contenu_yaml, *, verifier_seulement=False):
    contenu, identifiants = lire_source(contenu_yaml)
    metadata = contenu["source"]
    # Le verrou sérialise les imports successifs d'une source déjà créée.
    source = SourceReferentiel.objects.select_for_update().filter(identifiant=metadata["identifiant"]).first()
    if source and (source.ecole_id is not None or any(getattr(source, c) != metadata[c]
                      for c in ("titre", "provenance", "licence", "provisoire"))):
        raise ValidationError("La source existe avec une autre provenance ou description ; aucune modification effectuée.")
    empreinte = hashlib.sha256(json.dumps(contenu, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    version = source.versions.filter(numero=contenu["version"]).first() if source else None
    if version and (version.empreinte != empreinte or version.contenu != contenu):
        raise ValidationError("Cette version existe avec un autre contenu ; publier un nouveau numéro de version.")
    if verifier_seulement:
        return version, False, len(identifiants)
    if version:
        return version, False, len(identifiants)
    if source is None:
        source = SourceReferentiel(**metadata)
        source.full_clean()
        source.save()
    version = VersionReferentiel(source=source, numero=contenu["version"], empreinte=empreinte, contenu=contenu)
    version.full_clean()
    version.save()
    for identifiant_source in sorted(identifiants):
        identite, _ = IdentiteSourceCompetence.objects.get_or_create(source=source, identifiant=identifiant_source)
        definition = DefinitionSourceCompetence(identite=identite, version=version)
        definition.full_clean()
        definition.save()
    return version, True, len(identifiants)
