"""Comparaison en lecture seule de deux versions d'une même source."""
import hashlib
import json

from django.db.models import Q

from suivi.presentation import catalogue_icones
from suivi.models import AdaptationCompetence, Competence, CompetenceSourceEcole


def definitions(version):
    resultat = {}
    for domaine in version.contenu.get("domaines", []):
        groupes = [(None, domaine.get("competences", []))]
        groupes += [(s, s["competences"]) for s in domaine.get("sous_domaines", [])]
        for sous, competences in groupes:
            for c in competences:
                resultat[c["identite"]] = {**c, "domaine": domaine["nom"],
                    "sous_domaine": sous["nom"] if sous else "",
                    "attendus": domaine.get("attendus", []), "ordre": len(resultat)}
    return resultat


def apercu_mise_a_jour(classe, actuelle, version):
    if not actuelle or actuelle.version_id == version.pk or actuelle.version.source_id != version.source_id:
        return None
    if version.source.ecole_id is not None:
        return None  # Une reprise ancienne n'établit pas d'identités sources.
    avant, apres = definitions(actuelle.version), definitions(version)
    liaisons = dict(CompetenceSourceEcole.objects.filter(ecole=classe.ecole,
        identite__source=version.source).values_list("identite__identifiant", "competence_id"))
    regles = list(AdaptationCompetence.objects.filter(
        Q(classe__isnull=True) | Q(classe=classe), ecole=classe.ecole,
        annee_scolaire=classe.annee_scolaire, competence_id__in=liaisons.values()).order_by("pk"))
    empreinte = hashlib.sha256(json.dumps([(r.pk, r.revision) for r in regles]).encode()).hexdigest()
    materielles = Competence.objects.in_bulk(liaisons.values())
    champs = [("libelle", "Libellé"), ("code", "Code"), ("niveau", "Section"),
        ("domaine", "Domaine"), ("sous_domaine", "Sous-domaine"), ("attendus", "Attendus"),
        ("ordre", "Ordre de présentation"), ("icone", "Illustration proposée"), ("formulations", "Phrases proposées")]
    def texte(valeur):
        if isinstance(valeur, list):
            return " ; ".join(v["texte"] for v in valeur) or "Aucune proposition"
        return str(valeur) if valeur not in (None, "") else "Aucune proposition"

    communes = avant.keys() & apres.keys()
    # Comparer uniquement l'ordre relatif des identités conservées dans
    # chaque rubrique. Une insertion ou un retrait ne déplace pas les autres.
    def positions(definitions):
        rangs, resultat = {}, {}
        for identite, c in definitions.items():
            if identite not in communes:
                continue
            groupe = (c["domaine"], c["sous_domaine"])
            autre = apres[identite] if definitions is avant else avant[identite]
            if groupe != (autre["domaine"], autre["sous_domaine"]):
                continue
            rangs[groupe] = rangs.get(groupe, 0) + 1
            resultat[identite] = rangs[groupe]
        return resultat

    positions_avant, positions_apres = positions(avant), positions(apres)
    icones = catalogue_icones()
    modifiees, conservees = [], []
    for identite, nouveau in apres.items():
        ancien = avant.get(identite)
        locales = [r for r in regles if r.competence_id == liaisons.get(identite)
            and (r.libelle is not None or r.visible is not None)]
        adaptation = None
        if locales:
            # Résoudre dans le même ordre que le lecteur commun : école, classe.
            locales.sort(key=lambda r: r.classe_id is not None)
            libelle = nouveau["libelle"]
            competence = materielles.get(liaisons.get(identite))
            visible = bool(competence and competence.active)
            for r in locales:
                if r.libelle is not None:
                    libelle = r.libelle
                if r.visible is not None:
                    visible = r.visible
            adaptation = {"source": nouveau["libelle"], "libelle": libelle, "visible": visible}
            conservees.append(adaptation)
        if ancien:
            details = []
            for cle, nom in champs:
                v1, v2 = ancien.get(cle), nouveau.get(cle)
                if cle == "ordre":
                    v1, v2 = positions_avant.get(identite), positions_apres.get(identite)
                if v1 == v2:
                    continue
                detail = {"cle": cle, "champ": nom, "avant": texte(v1), "apres": texte(v2)}
                if cle == "icone":
                    detail.update(icone_avant=icones.get(v1), icone_apres=icones.get(v2))
                details.append(detail)
            if details:
                modifiees.append({"avant": ancien["libelle"], "apres": nouveau["libelle"],
                    "changements": [d["champ"] for d in details], "adaptation": adaptation,
                    "filtres": " ".join(d["cle"] for d in details), "details": details})
    # Un retrait ou un changement de section peut changer les possibilités de
    # saisie. Garder le garde-fou renforcé dans ces cas.
    continue_suivi = avant.keys() <= apres.keys() and all(
        ancien["niveau"] == apres[identite]["niveau"]
        for identite, ancien in avant.items()
    )
    return {"modifiees": modifiees, "adaptations": conservees,
        "continue_suivi": continue_suivi,
        "ajoutees": [c["libelle"] for i, c in apres.items() if i not in avant],
        "retirees": [c["libelle"] for i, c in avant.items() if i not in apres],
        "empreinte_adaptations": empreinte}
