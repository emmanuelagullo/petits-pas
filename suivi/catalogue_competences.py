"""Catalogue de classe commun au suivi ciblé et aux référentiels."""
import unicodedata

from django.db.models import Count, Q

from .autorisations import GERER_REFERENTIEL_CLASSE, autorise
from .models import AdaptationCompetence, CompetenceLocale, EleveApprentissage, Observation
from .navigation import lien
from .rubriques import origine_rubrique, rattachements_rubriques
from .referentiels import adoption_courante, arbre_version, arbre_competences, contenu_adoption, observations_classe
from .services.ajouts_referentiels import catalogue_reprises


def cle_libelle(texte):
    return " ".join(unicodedata.normalize("NFC", texte).casefold().split())


def cle_alphabetique(texte):
    return "".join(c for c in unicodedata.normalize("NFD", cle_libelle(texte))
                   if not unicodedata.combining(c))


def catalogue_classe(classe, utilisateur):
    adoption = adoption_courante(classe)
    if adoption:
        arbre = arbre_version(classe.ecole, contenu_adoption(adoption), masquer=False)
    else:
        arbre = arbre_competences(classe.ecole, classe=classe)
    competences = [competence for domaine in arbre for competence in domaine.visibles]
    presentes = {c.pk for c in competences}
    if adoption and not adoption.clos and autorise(utilisateur, GERER_REFERENTIEL_CLASSE, classe):
        disponibles = catalogue_reprises(utilisateur=utilisateur, ecole=classe.ecole,
            annee=classe.annee_scolaire, classe=classe).exclude(competence_id__in=presentes).select_related(
                "competence__domaine", "competence__sous_domaine")
        competences.extend(locale.competence for locale in disponibles)
    locales = {
        locale.competence_id: locale
        for locale in CompetenceLocale.objects.filter(ecole=classe.ecole, competence_id__in=[c.pk for c in competences])
    }
    comptes = dict(observations_classe(classe).filter(competence_id__in=presentes).filter(
        Q(statut_lecture__in=[Observation.EN_COURS, Observation.REUSSI])
        | Q(traces__scolarite__classe=classe, traces__supprime_le__isnull=True)
    ).order_by().values("competence_id").annotate(nombre=Count("eleve_id", distinct=True))
      .values_list("competence_id", "nombre"))
    suivis = dict(EleveApprentissage.objects.filter(
        disponibilite__classe=classe, scolarite__classe=classe,
        scolarite__eleve__archive_le__isnull=True, active=True,
        disponibilite__locale_id__in=[l.pk for l in locales.values() if l.suivi_libre],
    ).order_by().values("disponibilite__locale_id").annotate(nombre=Count("pk"))
      .values_list("disponibilite__locale_id", "nombre"))
    selections = dict(AdaptationCompetence.objects.filter(classe=classe, selection_eleves=True,
        competence_id__in=presentes).annotate(nombre=Count("eleves_selectionnes", filter=Q(
            eleves_selectionnes__active=True, eleves_selectionnes__scolarite__classe=classe,
            eleves_selectionnes__scolarite__eleve__archive_le__isnull=True,
        ))).values_list("competence_id", "nombre"))
    domaines = {d.pk: d for d in arbre}
    groupes = {s.pk: s for d in arbre for s in getattr(d, "sous_domaines_lus", [])}
    parents, enfants = rattachements_rubriques(adoption, list(domaines.values()), list(groupes.values()))
    resultats = []
    for competence in competences:
        locale = locales.get(competence.pk)
        portee = "cible" if competence.pk in selections or (locale and locale.suivi_libre) else "classe" if locale else "base"
        domaine = domaines.get(parents.get(competence.domaine_id), competence.domaine)
        sous = groupes.get(enfants.get(competence.sous_domaine_id), competence.sous_domaine)
        resultats.append({
            "competence": competence, "locale": locale, "portee": portee,
            "domaine": origine_rubrique(domaine) or domaine.nom,
            "domaine_affiche_id": domaine.pk,
            "sous_domaine": sous.nom if sous else "",
            "sous_domaine_affiche_id": sous.pk if sous else None,
            "nombre": comptes.get(competence.pk, 0),
            "suivis": selections.get(competence.pk, suivis.get(locale.pk, 0) if locale else 0),
            "disponible": competence.pk not in presentes,
            "url": (lien("ajouts_classe", classe.pk, ancre=f"ajout-{locale.pk}") if competence.pk not in presentes
                    else lien("saisie_competence", classe.pk, competence.pk)),
        })
    return sorted(resultats, key=lambda l: (
        cle_alphabetique(l["domaine"]), l["domaine"], l["domaine_affiche_id"], cle_alphabetique(l["sous_domaine"]),
        l["sous_domaine"], l["sous_domaine_affiche_id"] or 0, cle_alphabetique(l["competence"].libelle),
    ))


def doublons_classe(classe, libelle, utilisateur):
    cle = cle_libelle(libelle)
    return [ligne for ligne in catalogue_classe(classe, utilisateur) if cle_libelle(ligne["competence"].libelle) == cle]
