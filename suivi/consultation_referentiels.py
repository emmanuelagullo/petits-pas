"""Lecture du catalogue sans créer d'identités de suivi ni d'adoption."""
import re
import unicodedata

from .referentiels import contenu_adoption


def lignes_consultation(version, adoption=None):
    contenu = contenu_adoption(adoption) if adoption else version.contenu
    lignes = []
    if adoption or version.source.ecole_id is not None:
        domaines = {d["id"]: d["nom"] for d in contenu.get("domaines", [])}
        groupes = {s["id"]: s["nom"] for s in contenu.get("sous_domaines", [])}
        for c in contenu.get("competences", []):
            lignes.append({**c, "domaine": domaines.get(c["domaine_id"], ""),
                           "groupe": groupes.get(c.get("sous_domaine_id"), "")})
    else:
        for d in contenu.get("domaines", []):
            for groupe, competences in [("", d["competences"])] + [(s["nom"], s["competences"]) for s in d["sous_domaines"]]:
                for c in competences:
                    lignes.append({**c, "domaine": d["nom"], "groupe": groupe, "active": True})
    return lignes


def _normaliser(texte):
    return "".join(c for c in unicodedata.normalize("NFKD", texte.casefold())
                   if not unicodedata.combining(c))


def _distance(a, b):
    """Erreurs de frappe : ajout, retrait, remplacement ou inversion voisine."""
    ligne = list(range(len(b) + 1))
    precedente = None
    for i, lettre in enumerate(a, 1):
        suivante = [i]
        for j, autre in enumerate(b, 1):
            suivante.append(min(suivante[-1] + 1, ligne[j] + 1,
                                ligne[j - 1] + (lettre != autre)))
            if i > 1 and j > 1 and lettre == b[j - 2] and a[i - 2] == autre:
                suivante[-1] = min(suivante[-1], precedente[j - 2] + 1)
        precedente, ligne = ligne, suivante
    return ligne[-1]


def rechercher_apprentissages(lignes, recherche):
    """Tous les termes sont requis ; les correspondances exactes précèdent les proches."""
    termes = re.findall(r"\w+", _normaliser(recherche))
    if not termes:
        return lignes
    resultats = []
    for ligne in lignes:
        texte = _normaliser(ligne["libelle"])
        mots = re.findall(r"\w+", texte)
        score = 0
        for terme in termes:
            if terme in texte:
                continue
            # Pas de rapprochement hasardeux sur les termes courts.
            tolerance = 2 if len(terme) >= 9 else 1 if len(terme) >= 5 else 0
            if not tolerance:
                break
            proches = [_distance(terme, mot) for mot in mots
                       if abs(len(terme) - len(mot)) <= tolerance]
            distance = min(proches, default=tolerance + 1)
            if distance > tolerance:
                break
            score += distance
        else:
            resultats.append((score, ligne))
    return [ligne for _, ligne in sorted(resultats, key=lambda r: r[0])]
