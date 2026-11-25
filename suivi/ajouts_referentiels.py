"""Composition en lecture des ajouts retenus ; aucune modification des sources."""
from copy import deepcopy
from .models import DisponibiliteCompetenceLocale


def definition_effective_ajout(locale):
    """Utiliser le classement courant sans réécrire la définition d’origine."""
    resultat = deepcopy(locale.definition)
    competence = locale.competence
    domaine = competence.domaine
    sous = competence.sous_domaine
    resultat["domaines"] = [{"id": domaine.pk, "code": domaine.code, "nom": domaine.nom, "ordre": domaine.ordre}]
    resultat["sous_domaines"] = [{"id": sous.pk, "code": sous.code, "nom": sous.nom,
         "domaine_id": sous.domaine_id, "ordre": sous.ordre}] if sous else []
    resultat["competences"][0].update(niveau=competence.niveau, domaine_id=domaine.pk,
                                      sous_domaine_id=competence.sous_domaine_id)
    return resultat


def contenu_avec_ajouts(contenu, classe):
    resultat = deepcopy(contenu)
    for choix in DisponibiliteCompetenceLocale.objects.filter(classe=classe,
            annee_scolaire=classe.annee_scolaire, locale__ecole_id=classe.ecole_id).select_related("locale__competence__domaine", "locale__competence__sous_domaine").order_by("pk"):
        definition = definition_effective_ajout(choix.locale)
        for rubrique in ("domaines", "sous_domaines", "competences", "formulations"):
            ids = {c["id"] for c in resultat.setdefault(rubrique, [])}
            resultat[rubrique].extend(c for c in definition.get(rubrique, []) if c["id"] not in ids)
    return resultat
