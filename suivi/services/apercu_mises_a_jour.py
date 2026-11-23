"""Comparaison en lecture seule de deux versions d'une même source."""
import hashlib
import json

from django.db.models import Q

from suivi.identites_referentiels import reference_competence, references_suivi
from suivi.presentation import catalogue_icones
from suivi.models import AdaptationCompetence, Competence, FormulationLocale, ReglagePresentation


def definitions(version):
    resultat = {}
    for domaine in version.contenu.get("domaines", []):
        groupes = [(None, domaine.get("competences", []))]
        groupes += [(s, s["competences"]) for s in domaine.get("sous_domaines", [])]
        for sous, competences in groupes:
            for c in competences:
                resultat[reference_competence(c)] = {**c, "domaine": domaine["nom"],
                    "sous_domaine": sous["nom"] if sous else "",
                    "attendus": domaine.get("attendus", []), "ordre": len(resultat)}
    return resultat


def apercu_mise_a_jour(classe, actuelle, version):
    if not actuelle or actuelle.version_id == version.pk or actuelle.version.source_id != version.source_id:
        return None
    if version.source.ecole_id is not None:
        return None  # Une reprise ancienne n'établit pas d'identités sources.
    avant, apres = definitions(actuelle.version), definitions(version)
    liaisons = references_suivi(classe.ecole, actuelle.version) | references_suivi(classe.ecole, version)
    regles = list(AdaptationCompetence.objects.filter(
        Q(classe__isnull=True) | Q(classe=classe), ecole=classe.ecole,
        annee_scolaire=classe.annee_scolaire, competence_id__in=liaisons.values()).order_by("pk"))
    phrases_locales = list(FormulationLocale.objects.filter(
        Q(classe__isnull=True) | Q(classe=classe), ecole=classe.ecole,
        competence_id__in=liaisons.values(), origine__isnull=False
    ).select_related("origine").order_by("pk"))
    empreinte = hashlib.sha256(json.dumps([
        [(r.pk, r.revision) for r in regles],
        [(r.pk, r.mode, r.texte, r.classe_id, r.origine_id) for r in phrases_locales],
    ]).encode()).hexdigest()
    phrases_par_competence = {}
    for r in phrases_locales:
        phrases_par_competence.setdefault(r.competence_id, {}).setdefault(r.origine.code, {})[r.classe_id] = r
    phrases_reprenables = {}
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
    modifiees, conservees, libelles_reprenables = [], [], {}
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
            choix_libelle = None
            if ancien["libelle"] != nouveau["libelle"]:
                choix_classe = next((r for r in locales if r.classe_id and r.libelle is not None), None)
                choix_ecole = next((r for r in locales if not r.classe_id and r.libelle is not None), None)
                if choix_classe:
                    choix_libelle = {"id": choix_classe.competence_id,
                                    "revision": choix_classe.revision,
                                    "visible": choix_classe.visible,
                                    "apres": choix_ecole.libelle if choix_ecole else nouveau["libelle"]}
                    libelles_reprenables[str(choix_classe.competence_id)] = choix_libelle
            choix_phrases = []
            formulations_avant = {f["code"]: f["texte"] for f in ancien["formulations"]}
            for phrase in nouveau["formulations"]:
                code = phrase["code"]
                if code not in formulations_avant or phrase["texte"] == formulations_avant[code]:
                    continue
                regles_phrase = phrases_par_competence.get(liaisons.get(identite), {}).get(code, {})
                locale = regles_phrase.get(classe.pk)
                if not locale or locale.mode != ReglagePresentation.REMPLACER:
                    continue
                ecole = regles_phrase.get(None)
                choix = {"id": locale.origine_id, "competence_id": locale.competence_id,
                         "avant": locale.texte, "apres": phrase["texte"], "masquee": False}
                if ecole and ecole.mode == ReglagePresentation.REMPLACER:
                    choix["apres"] = ecole.texte
                elif ecole and ecole.mode == ReglagePresentation.DESACTIVER:
                    choix["masquee"] = True
                choix_phrases.append(choix)
                phrases_reprenables[str(locale.origine_id)] = choix
            if details:
                modifiees.append({"avant": ancien["libelle"], "apres": nouveau["libelle"],
                    "changements": [d["champ"] for d in details], "adaptation": adaptation,
                    "choix_libelle": choix_libelle, "choix_phrases": choix_phrases,
                    "filtres": " ".join(d["cle"] for d in details), "details": details})
    # Un retrait ou un changement de section peut changer les possibilités de
    # saisie. Garder le garde-fou renforcé dans ces cas.
    continue_suivi = avant.keys() <= apres.keys() and all(
        ancien["niveau"] == apres[identite]["niveau"]
        for identite, ancien in avant.items()
    )
    return {"modifiees": modifiees, "adaptations": conservees,
        "phrases_reprenables": phrases_reprenables,
        "continue_suivi": continue_suivi, "libelles_reprenables": libelles_reprenables,
        "ajoutees": [c["libelle"] for i, c in apres.items() if i not in avant],
        "retirees": [c["libelle"] for i, c in avant.items() if i not in apres],
        "empreinte_adaptations": empreinte}
