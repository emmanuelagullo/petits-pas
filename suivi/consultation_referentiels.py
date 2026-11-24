"""Lecture du catalogue sans créer d'identités de suivi ni d'adoption."""
import re
import unicodedata

from .referentiels import contenu_adoption
from .services.apercu_mises_a_jour import definitions_document


def lignes_consultation(version, adoption=None):
    contenu = contenu_adoption(adoption) if adoption else version.contenu
    lignes = []
    if adoption or contenu.get("origine") != "source_declaree":
        domaines = {d["id"]: d["nom"] for d in contenu.get("domaines", [])}
        groupes = {s["id"]: s["nom"] for s in contenu.get("sous_domaines", [])}
        def rangs(rubriques):
            return {r["id"]: i for i, r in enumerate(rubriques)}
        ordre_domaines = rangs(contenu.get("domaines", []))
        ordre_groupes = rangs(contenu.get("sous_domaines", []))
        for c in sorted(contenu.get("competences", []), key=lambda c: (
            ordre_domaines.get(c["domaine_id"], len(ordre_domaines)),
            ordre_groupes.get(c.get("sous_domaine_id"), -1),
        )):
            lignes.append({**c, "domaine": domaines.get(c["domaine_id"], ""),
                           "sous_domaine": groupes.get(c.get("sous_domaine_id"), ""),
                           "domaine_affiche_id": c["domaine_id"], "sous_domaine_affiche_id": c.get("sous_domaine_id")})
    else:
        lignes = [{**definition, "active": True} for definition in definitions_document(contenu).values()]
    from .models import CompetenceLocale
    libres = set(CompetenceLocale.objects.filter(suivi_libre=True).values_list("competence_id", flat=True))
    return [c for c in lignes if c.get("id") not in libres]


def _normaliser(texte):
    return "".join(c for c in unicodedata.normalize("NFKD", texte.casefold())
                   if not unicodedata.combining(c))


def cle_recherche_libelle(texte):
    """Égalité de libellé indépendante des accents, de la casse et du séparateur."""
    return " ".join(re.findall(r"[^\W_]+", _normaliser(texte)))


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


def classement_rubrique(ligne):
    return (ligne.get("domaine_affiche_id", ligne["domaine"]),
            ligne.get("sous_domaine_affiche_id", ligne["sous_domaine"]))


def recherche_par_rubriques(lignes, recherche, *, texte=None):
    """Conserver l’ordre de lecture des rubriques et classer les résultats dans chacune."""
    if not recherche:
        return lignes
    ordre = {cle: i for i, cle in enumerate(dict.fromkeys(map(classement_rubrique, lignes)))}
    index = [{"libelle": texte(ligne) if texte else ligne["libelle"], "ligne": ligne} for ligne in lignes]
    resultats = (item["ligne"] for item in rechercher_apprentissages(index, recherche))
    return sorted(resultats, key=lambda ligne: ordre[classement_rubrique(ligne)])


def rechercher_apprentissages(lignes, recherche):
    """Tous les termes sont requis ; les correspondances exactes précèdent les proches."""
    termes = re.findall(r"\w+", _normaliser(recherche))
    if not termes:
        return lignes
    exacte = cle_recherche_libelle(recherche)
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
            resultats.append(((cle_recherche_libelle(texte) != exacte, score), ligne))
    return [ligne for _, ligne in sorted(resultats, key=lambda r: r[0])]


def liens_documentaires(source):
    """Liens explicites des références connues, sans réécrire les métadonnées."""
    documents = [
        ("BO n°41 du 31 octobre 2024", "https://www.education.gouv.fr/bo/2024/Hebdo41/MENE2415135A"),
        ("BO n°19 du 7 mai 2026", "https://www.education.gouv.fr/bo/2026/Hebdo19/MENE2608627A"),
        ("BO n°6 du 6 février 2025", "https://www.education.gouv.fr/bo/2025/Hebdo6/MENE2503064A"),
        ("referentiel/cycle1/NOTICE.org", "https://petits-pas.gitlabpages.inria.fr/petits-pas/referentiels/cycle1/NOTICE.org"),
        ("REGISTRE.csv", "https://petits-pas.gitlabpages.inria.fr/petits-pas/referentiels/cycle1/REGISTRE.csv"),
    ]
    licences = [
        ("Etalab-2.0", "https://github.com/etalab/licence-ouverte/blob/master/LO.md"),
        ("CC-BY-SA-4.0", "https://creativecommons.org/licenses/by-sa/4.0/deed.fr"),
    ]
    return {
        "documents": [(titre, url) for titre, url in documents if titre in source.provenance],
        "licences": [(titre, url) for titre, url in licences if titre in source.licence],
    }
