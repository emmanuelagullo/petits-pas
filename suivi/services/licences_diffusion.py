"""Conditions de diffusion transportées par le document commun au ZIP et à Grist."""
from collections import Counter

from suivi.identites_referentiels import competences_document

LICENCE_PROPOSEE = "CC-BY-SA-4.0"
LICENCES_RECONNUES = {"CC0-1.0", "CC-BY-4.0", LICENCE_PROPOSEE, "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0"}
LICENCE_ORIGINE_NON_RENSEIGNEE = "Licence d’origine non renseignée"
INCONNUES = {"", "non renseignée", "non renseigné", "inconnue", "à vérifier"}


def licence_renseignee(licence):
    licence = licence.strip()
    return licence if licence.casefold() not in INCONNUES else ""


def resoudre_licence(licence="", *, origine="", creation=False, defaut_creation=LICENCE_PROPOSEE):
    """Renvoyer la notice effective et signaler le recours à un défaut."""
    for valeur in (licence, origine):
        renseignee = licence_renseignee(valeur or "")
        if renseignee and renseignee != LICENCE_ORIGINE_NON_RENSEIGNEE:
            return renseignee, False
    if creation:
        return licence_renseignee(defaut_creation) or LICENCE_PROPOSEE, True
    return LICENCE_ORIGINE_NON_RENSEIGNEE, True


def droits_competence(document, competence):
    source = document["source"]
    droits = document.get("droits", {})
    cle = competence.get("droits") or competence.get("source_origine")
    licence, credits = droits.get(cle, (source["licence"], source["provenance"]))
    return licence_renseignee(licence), credits


def encoder_droits(document, par_code, *, conserver_defaut=False):
    """Mutualiser par provenance et n'écrire une clé individuelle qu'en dernier recours."""
    competences = list(competences_document(document))
    if not competences:
        return
    source = document["source"]
    defaut = (source["licence"], source["provenance"])
    variantes = Counter(par_code.values())
    if not conserver_defaut and defaut not in variantes and len(variantes) == 1:
        defaut, = variantes
        source["licence"], source["provenance"] = defaut
    par_origine = {}
    for c in competences:
        origine = c.get("source_origine")
        if origine:
            par_origine.setdefault(origine, set()).add(par_code[c["code"]])
    tailles = Counter(c.get("source_origine") for c in competences)
    notices, cles = {}, {}
    for origine, choix in sorted(par_origine.items(), key=lambda item: -tailles[item[0]]):
        if len(choix) != 1 or defaut in choix:
            continue
        notice, = choix
        # Une courte référence coûte moins que recopier une longue notice
        # lorsque plusieurs provenances renvoient aux mêmes crédits.
        if notice in cles and tailles[origine] * (12 + len(cles[notice])) < len(origine) + sum(map(len, notice)):
            continue
        notices[origine] = notice
        cles.setdefault(notice, origine)
    for c in competences:
        notice = par_code[c["code"]]
        c.pop("droits", None)
        if notice == notices.get(c.get("source_origine"), defaut):
            continue
        if notice not in cles:
            cle = f"_{len(notices) + 1}"
            notices[cle] = notice
            cles[notice] = cle
        c["droits"] = cles[notice]
    if notices:
        document["droits"] = notices
    else:
        document.pop("droits", None)
