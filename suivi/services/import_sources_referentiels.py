"""Import au catalogue : aucune adoption ni écriture dans le suivi des élèves."""
import hashlib
import json
import re

import yaml
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from suivi.models import (DefinitionSourceCompetence, IdentiteSourceCompetence,
                          SourceReferentiel, VersionReferentiel)
from suivi.identites_referentiels import competences_document, est_uuid_portable, identifiant_source_classe, identifiant_source_ecole, reference_competence
from suivi.icones_partagees import conserver_png, decoder_icone, encoder_icone, png_en_ligne
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


def normaliser_filiation(valeur):
    filiation = objet(valeur, ("source", "identite", "edition", "libelle"), "Variante")
    return {
        "source": identifiant(filiation.get("source"), "Source de la variante"),
        "identite": identifiant(filiation.get("identite"), "Identité d’origine"),
        "edition": identifiant(filiation.get("edition"), "Édition d’origine", 80),
        "libelle": texte(filiation.get("libelle"), "Libellé d’origine", 300),
    }


def normaliser(document):
    document = objet(document, ("format", "source", "version", "domaines", "structure_seule", "droits"), "Document")
    if type(document.get("format")) is not int or document["format"] not in (1, 2):
        raise ValidationError("Format attendu : 1 ou 2.")
    source = objet(document.get("source"), ("identifiant", "titre", "provenance", "licence", "provisoire"), "Source")
    source = {"identifiant": identifiant(source.get("identifiant"), "Identifiant de source"),
              "titre": texte(source.get("titre"), "Titre"),
              "provenance": texte(source.get("provenance"), "Provenance", 4000),
              "licence": texte(source.get("licence"), "Licence", 120),
              "provisoire": source.get("provisoire")}
    if source["identifiant"].startswith(("reprise-ecole-", "catalogue-ecole-")):
        raise ValidationError("Cet identifiant est réservé aux reprises de bases existantes.")
    if type(source["provisoire"]) is not bool:
        raise ValidationError("Provisoire doit valoir true ou false.")
    droits = document.get("droits", {})
    if not isinstance(droits, dict):
        raise ValidationError("Les droits de diffusion doivent être associés à une provenance.")
    droits = {
        texte(cle, "Référence de droits", 120): [
            texte(notice[0], "Licence", 120, facultatif=True),
            texte(notice[1], "Crédits", 4000, facultatif=True),
        ] if isinstance(notice, (list, tuple)) and len(notice) == 2 else None
        for cle, notice in droits.items()
    }
    if None in droits.values():
        raise ValidationError("Chaque notice de diffusion doit contenir une licence et des crédits.")
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
            champs = ("identite", "code", "libelle", "niveau", "icone", "formulations")
            if document["format"] == 2:
                champs += ("source_origine", "icone_png", "variante_de", "active", "droits")
            c = objet(c, champs, "Compétence")
            identite = identifiant(c.get("identite"), "Identité")
            origine = {}
            if "source_origine" in c:
                origine_source = identifiant(c["source_origine"], "Source d’origine")
                if origine_source != source["identifiant"]:
                    origine["source_origine"] = origine_source
            unique(reference_competence({"identite": identite, **origine}), identites, "Identité")
            code = unique(identifiant(c.get("code"), "Code de compétence", 20), codes_competences, "Code de compétence")
            niveau = c.get("niveau", "PS")
            if niveau not in ("PS", "MS", "GS"):
                raise ValidationError("Niveau attendu : PS, MS ou GS.")
            icone = texte(c.get("icone", ""), "Icône", 120, facultatif=True)
            if icone and icone not in catalogue_icones():
                raise ValidationError(f"Icône inconnue : {icone}.")
            personnalisee = {}
            if "droits" in c:
                cle_droits = texte(c["droits"], "Référence de droits", 120)
                if cle_droits not in droits:
                    raise ValidationError("Une notice de diffusion référencée est absente.")
                personnalisee["droits"] = cle_droits
            if "active" in c:
                if type(c["active"]) is not bool:
                    raise ValidationError("La disponibilité doit être vraie ou fausse.")
                personnalisee["active"] = c["active"]
            if "variante_de" in c:
                personnalisee["variante_de"] = normaliser_filiation(c["variante_de"])
            if "icone_png" in c:
                if icone:
                    raise ValidationError("Choisissez une seule illustration pour cette compétence.")
                personnalisee["icone_png"] = encoder_icone(decoder_icone(c["icone_png"]))
            formulations, codes_phrases = [], set()
            for f in liste(c.get("formulations", []), "Phrases proposées"):
                f = objet(f, ("code", "texte"), "Phrase proposée")
                formulations.append({"code": unique(identifiant(f.get("code"), "Code de phrase", 80), codes_phrases, "Code de phrase"),
                                     "texte": texte(f.get("texte"), "Phrase proposée", 4000)})
            resultat.append({**origine, **personnalisee, "identite": identite, "code": code, "libelle": texte(c.get("libelle"), "Libellé", 300),
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
    structure = document.get("structure_seule", False)
    if type(structure) is not bool or (structure and identites):
        raise ValidationError("Une structure seule ne contient aucune compétence.")
    if not domaines or (not structure and not identites):
        raise ValidationError("Au moins un domaine et une compétence sont nécessaires.")
    contenu = {"format": document["format"], "origine": "source_declaree", "source": source, "version": numero, "domaines": domaines}
    if droits:
        contenu["droits"] = droits
    if structure:
        contenu["structure_seule"] = True
    return contenu, identites


def lire_source(contenu_yaml):
    try:
        document = yaml.load(contenu_yaml, Loader=ChargeurSansDoublons)
    except yaml.YAMLError as erreur:
        raise ValidationError("Le fichier YAML est invalide.") from erreur
    return normaliser(document)


@transaction.atomic
def importer_source(contenu_yaml, *, verifier_seulement=False, ecole=None, classe=None):
    if classe is not None and (ecole is None or classe.ecole_id != ecole.pk):
        raise ValidationError("La classe n’appartient pas à cette école.")
    contenu, identifiants = lire_source(contenu_yaml)
    if ecole is not None:
        type(ecole).objects.select_for_update().get(pk=ecole.pk)
    metadata = contenu["source"]
    # Le verrou sérialise les imports successifs d'une source déjà créée.
    identifiant = metadata["identifiant"]
    if classe:
        identifiant = identifiant_source_classe(classe, identifiant)
    elif ecole is not None:
        identifiant = identifiant_source_ecole(ecole, identifiant)
    source = SourceReferentiel.objects.select_for_update().filter(identifiant=identifiant).first()
    provenance_a_completer = bool(source and ecole and not source.versions.exists()
                                  and source.provenance == "" and source.licence == "")
    if source and not provenance_a_completer and (source.ecole_id != (ecole.pk if ecole else None) or any(getattr(source, c) != metadata[c]
                      for c in ("titre", "provenance", "licence", "provisoire"))):
        raise ValidationError("La source existe avec une autre provenance ou description ; aucune modification effectuée.")
    empreinte = hashlib.sha256(json.dumps(contenu, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    version = source.versions.filter(numero=contenu["version"]).first() if source else None
    if version:
        from copy import deepcopy
        precedente = deepcopy(version.contenu)
        for c in competences_document(precedente):
            if c.get("icone_png"):
                c["icone_png"] = png_en_ligne(c["icone_png"])
    if version and precedente != contenu:
        raise ValidationError("Cette version existe avec un autre contenu ; publier un nouveau numéro de version.")
    empruntees = {}
    origines_manquantes = {}
    for competence in competences_document(contenu):
        cle_portable = competence["identite"]
        if ecole is not None and est_uuid_portable(cle_portable):
            identites_portables = list(IdentiteSourceCompetence.objects.filter(
                source__ecole=ecole, identifiant=cle_portable,
            ).order_by("pk")[:2])
            if len(identites_portables) > 1 and not version:
                raise ValidationError(f"Plusieurs origines locales portent le même UUID : {cle_portable}.")
            if identites_portables:
                empruntees[cle_portable] = identites_portables[0]
            continue
        if "source_origine" not in competence:
            continue
        identifiant_origine = competence["source_origine"]
        perimetre = Q(source__identifiant=identifiant_origine, source__ecole__isnull=True)
        if ecole is not None:
            perimetre |= Q(source__identifiant=identifiant_source_ecole(ecole, identifiant_origine),
                           source__ecole=ecole)
        origine = IdentiteSourceCompetence.objects.filter(perimetre, identifiant=competence["identite"]
            ).order_by(models.F("source__ecole_id").asc(nulls_last=True), "pk").first()
        reference = reference_competence(competence)
        if origine is None:
            if ecole is None or identifiant_origine.startswith(("reprise-ecole-", "catalogue-ecole-")):
                raise ValidationError(f"Identité d’origine inconnue : {reference}.")
            origines_manquantes[reference] = (identifiant_origine, competence["identite"])
        else:
            empruntees[reference] = origine
    if verifier_seulement:
        return version, False, len(identifiants)
    if version:
        return version, False, len(identifiants)
    historique_avant = {}
    if source is not None:
        from .heritage_sources import memoriser_avant_nouvelle_edition, relever_heritage

        historique_avant = relever_heritage(source=source)
        memoriser_avant_nouvelle_edition(source)
    if source is None:
        source = SourceReferentiel(**{**metadata, "identifiant": identifiant}, ecole=ecole,
                                   identifiant_diffusion=metadata["identifiant"] if ecole else "", classe_privee=classe)
        source.full_clean()
        source.save()
    if provenance_a_completer:
        for champ in ("titre", "provenance", "licence", "provisoire"):
            setattr(source, champ, metadata[champ])
        source.full_clean()
        source.save(update_fields=["titre", "provenance", "licence", "provisoire"])
    for reference, (identifiant_origine, cle) in origines_manquantes.items():
        origine, _ = SourceReferentiel.objects.get_or_create(
            identifiant=identifiant_source_ecole(ecole, identifiant_origine), ecole=ecole,
            defaults={"identifiant_diffusion": identifiant_origine, "titre": identifiant_origine},
        )
        empruntees[reference], _ = IdentiteSourceCompetence.objects.get_or_create(
            source=origine, identifiant=cle)
    from suivi.models import IconePartagee
    conserver_png(contenu, IconePartagee)
    version = VersionReferentiel(source=source, numero=contenu["version"], empreinte=empreinte, contenu=contenu)
    version.full_clean()
    version.save()
    for identifiant_source in sorted(identifiants):
        identite = empruntees.get(identifiant_source)
        if identite is None:
            identite, _ = IdentiteSourceCompetence.objects.get_or_create(source=source, identifiant=identifiant_source)
        definition = DefinitionSourceCompetence(identite=identite, version=version)
        definition.full_clean()
        definition.save()
    from .heritage_sources import preparer_phrases_heritees

    preparer_phrases_heritees(version)
    if historique_avant:
        from .heritage_sources import consigner_heritage

        consigner_heritage(historique_avant, relever_heritage(source=source), nom_source=source.titre)
    return version, True, len(identifiants)
