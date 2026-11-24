"""Contributions immuables et réconciliation des éditions d'équipe."""
import hashlib
import json
import re

from django.core.exceptions import ValidationError

from suivi.services.fusion_referentiel_equipe import fusionner_referentiel_equipe
from suivi.services.import_sources_referentiels import normaliser

_EMPREINTE = re.compile(r"[0-9a-f]{64}")


def identifiant_contribution(edition):
    contenu = json.dumps(edition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(contenu.encode()).hexdigest()


def contribution(parents, document):
    """Déduplique les envois après interruption, indépendamment de l'ordre des parents."""
    return {"parents": sorted(set(parents)), "document": document}


def verifier_contribution(empreinte, edition):
    if not isinstance(edition, dict) or set(edition) != {"parents", "document"}:
        raise ValidationError("Contribution d’équipe illisible.")
    parents = edition["parents"]
    if (not isinstance(parents, list) or len(parents) > 2
            or any(not isinstance(parent, str) or not _EMPREINTE.fullmatch(parent) for parent in parents)
            or parents != sorted(set(parents))):
        raise ValidationError("Versions parentes de la contribution illisibles.")
    if identifiant_contribution(edition) != empreinte:
        raise ValidationError("L’empreinte de la contribution ne correspond pas à son contenu.")
    normaliser(edition["document"])


def terminaisons(editions):
    """Calcule les têtes après réception de toutes les dépendances, sans ordre d’arrivée."""
    parents = {parent for edition in editions.values() for parent in edition["parents"]}
    if parents - editions.keys():
        raise ValidationError("Il manque des contributions antérieures dans le journal.")
    return sorted(editions.keys() - parents)


def ancetres(editions, identifiant):
    visites = set()
    a_visiter = [identifiant]
    while a_visiter:
        courant = a_visiter.pop()
        if courant in visites:
            continue
        visites.add(courant)
        a_visiter.extend(editions[courant]["parents"])
    return visites


def fusionner_tetes(editions, a, b):
    """Réconcilie deux contributions qui ont un ancêtre commun unique."""
    communs = ancetres(editions, a) & ancetres(editions, b)
    bases = communs - {parent for enfant in communs for parent in editions[enfant]["parents"]}
    if len(bases) != 1:
        raise ValidationError("Ces contributions n’ont pas de version commune unique.")
    base = bases.pop()
    resultat, conflits = fusionner_referentiel_equipe(
        editions[base]["document"], editions[a]["document"], editions[b]["document"],
    )
    if conflits:
        return None, conflits
    resultat["version"] = "fusion-" + hashlib.sha256(("".join(sorted([a, b]))).encode()).hexdigest()
    normaliser(resultat)
    return contribution((a, b), resultat), []
