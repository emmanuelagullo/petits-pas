"""Comparaison en lecture seule de deux versions d'une même source."""
import hashlib
import json

from django.db.models import Q

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

    modifiees, conservees = [], []
    for identite, nouveau in apres.items():
        ancien = avant.get(identite)
        locales = [r for r in regles if r.competence_id == liaisons.get(identite)
            and (r.libelle is not None or r.visible is not None)]
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
            conservees.append({"source": nouveau["libelle"], "libelle": libelle, "visible": visible})
        if ancien:
            changements = [nom for cle, nom in champs if ancien.get(cle) != nouveau.get(cle)]
            if changements:
                modifiees.append({"avant": ancien["libelle"], "apres": nouveau["libelle"],
                    "changements": changements, "adaptation": bool(locales),
                    "details": [{"champ": nom, "avant": texte(ancien.get(cle)),
                        "apres": texte(nouveau.get(cle))} for cle, nom in champs
                        if ancien.get(cle) != nouveau.get(cle)]})
    return {"modifiees": modifiees, "adaptations": conservees,
        "ajoutees": [c["libelle"] for i, c in apres.items() if i not in avant],
        "retirees": [c["libelle"] for i, c in avant.items() if i not in apres],
        "empreinte_adaptations": empreinte}
