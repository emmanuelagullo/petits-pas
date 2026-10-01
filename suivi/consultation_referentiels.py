"""Lecture du catalogue sans créer d'identités de suivi ni d'adoption."""
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
