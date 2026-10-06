"""Contenus fournis par le YAML et résolution des adaptations locales."""
from dataclasses import dataclass
from functools import lru_cache

import yaml
from django.conf import settings
from django.db.models import Q

from .models import FormulationLocale, ReglagePresentation


@lru_cache(maxsize=1)
def catalogue_icones():
    chemin = settings.BASE_DIR / "referentiel" / "icones.yaml"
    if not chemin.exists():
        return {}
    with chemin.open(encoding="utf-8") as fichier:
        return yaml.safe_load(fichier).get("icones", {})


@dataclass(frozen=True)
class Illustration:
    provenance: str = "Référentiel importé"
    icone: str = ""
    photo: str = ""
    reglage_id: int | None = None
    ressource_id: int | None = None

    @property
    def statique(self):
        return catalogue_icones().get(self.icone, {}).get("fichier", "")


def reglages_du_perimetre(ecole, classe=None):
    filtre = Q(classe__isnull=True)
    if classe is not None:
        filtre |= Q(classe=classe)
    return {(r.classe_id, r.competence_id): r
            for r in ReglagePresentation.objects.filter(filtre, ecole=ecole)}


def illustration_effective(ecole, competence=None, classe=None, reglages=None, historique=False):
    if classe is not None:
        if classe.ecole_id != ecole.pk:
            raise ValueError("Classe d'une autre école.")
        from .referentiels import adoption_courante
        adoption = adoption_courante(classe)
        if adoption and adoption.clos:
            donnees = (adoption.etat_final.get("illustrations", {}).get(str(competence.pk), {})
                       if competence else adoption.etat_final.get("couverture", {}))
            return Illustration(**donnees)
        if adoption and historique:
            # La reprise conserve les réglages disponibles, sans prétendre
            # reconstituer ceux qui avaient déjà été remplacés.
            identifiant = competence.pk if competence else None
            resultat = Illustration(icone=competence.icone if competence else "")
            for classe_id, provenance in [(None, "École"), (classe.pk, "Classe")]:
                for reglage in adoption.annuel.etat_initial.get("reglages", []):
                    if reglage["classe_id"] != classe_id or reglage["competence_id"] != identifiant:
                        continue
                    if reglage["mode"] == ReglagePresentation.HERITER:
                        continue
                    resultat = Illustration(provenance=provenance)
                    if reglage["mode"] == ReglagePresentation.REMPLACER:
                        from .models import RessourceReferentiel
                        ressource = (RessourceReferentiel.objects.filter(annuel=adoption.annuel,
                                     fichier=reglage["photo"]).first() if reglage["photo"] else None)
                        resultat = Illustration(provenance=provenance, icone=reglage["icone"],
                            photo=reglage["photo"], ressource_id=ressource.pk if ressource else None)
            return resultat
    if competence and classe:
        from .referentiels import definition_classe
        contenu = getattr(competence, "_contenu_referentiel", None) or definition_classe(classe, competence)
        if contenu and contenu.get("origine") == "source_declaree":
            from copy import copy
            competence = copy(competence)
            competence.icone = next(c["icone"] for c in contenu["competences"] if c["id"] == competence.pk)
    reglages = reglages if reglages is not None else reglages_du_perimetre(ecole, classe)
    resultat = Illustration(icone=competence.icone if competence else "")
    identifiant = competence.pk if competence else None
    niveaux = [(None, "École")]
    if classe is not None:
        if classe.ecole_id != ecole.pk:
            raise ValueError("Classe d'une autre école.")
        niveaux.append((classe.pk, "Classe"))
    for classe_id, provenance in niveaux:
        reglage = reglages.get((classe_id, identifiant))
        if reglage is None or reglage.mode == ReglagePresentation.HERITER:
            continue
        resultat = Illustration(provenance=provenance)
        if reglage.mode == ReglagePresentation.REMPLACER:
            resultat = Illustration(
                provenance=provenance,
                icone=reglage.icone,
                photo=reglage.photo.name if reglage.photo else "",
                reglage_id=reglage.pk,
            )
    return resultat


def propositions(competence, classe=None, inclure_masquees=False):
    ecole = competence.domaine.ecole
    if classe is not None and classe.ecole_id != ecole.pk:
        raise ValueError("Classe d'une autre école.")
    if classe is not None:
        from .referentiels import adoption_courante
        adoption = adoption_courante(classe)
        if adoption and adoption.clos:
            entrees = adoption.etat_final.get("propositions", {}).get(str(competence.pk), [])
            return [dict(e) for e in entrees if inclure_masquees or not e["masquee"]]
    filtre = Q(classe__isnull=True)
    if classe is not None:
        filtre |= Q(classe=classe)
    locales = list(FormulationLocale.objects.filter(filtre, competence=competence, ecole=ecole))
    entrees = {}
    bases = competence.formulations.all()
    if classe:
        from .referentiels import definition_classe
        contenu = getattr(competence, "_contenu_referentiel", None) or definition_classe(classe, competence)
        if contenu and contenu.get("origine") == "source_declaree":
            from types import SimpleNamespace
            bases = [SimpleNamespace(pk=f["id"], texte=f["texte"], active=f["active"])
                     for f in contenu["formulations"] if f["competence_id"] == competence.pk]
    for base in bases:
        entrees[f"base-{base.pk}"] = {
            "cle": f"base-{base.pk}", "texte": base.texte,
            "provenance": "Référentiel importé", "masquee": not base.active,
        }
    for classe_id, provenance in [(None, "École")] + ([(classe.pk, "Classe")] if classe else []):
        for locale in locales:
            if locale.classe_id != classe_id:
                continue
            cle = (f"base-{locale.origine_id}" if locale.origine_id else
                   f"locale-{locale.origine_locale_id or locale.pk}")
            if locale.origine_id or locale.origine_locale_id:
                if cle not in entrees:
                    continue
            else:
                entrees[cle] = {"cle": cle, "texte": locale.texte,
                                "provenance": provenance, "masquee": False}
            if locale.mode == ReglagePresentation.HERITER:
                continue
            entrees[cle]["masquee"] = locale.mode == ReglagePresentation.DESACTIVER
            entrees[cle]["provenance"] = provenance
            if locale.mode == ReglagePresentation.REMPLACER:
                entrees[cle]["texte"] = locale.texte
    # L'écran de réglage doit distinguer une adaptation de l'héritage effectif.
    niveau = classe.pk if classe else None
    for entree in entrees.values():
        entree["mode"] = ReglagePresentation.HERITER
        entree["ajoutee_ici"] = False
        for locale in locales:
            cle = (f"base-{locale.origine_id}" if locale.origine_id else
                   f"locale-{locale.origine_locale_id or locale.pk}")
            if locale.classe_id == niveau and cle == entree["cle"]:
                entree["mode"] = locale.mode
                entree["ajoutee_ici"] = not (locale.origine_id or locale.origine_locale_id)
                if locale.texte:
                    entree["texte_local"] = locale.texte
    return [e for e in entrees.values() if inclure_masquees or not e["masquee"]]


def formulations_effectives(competence, classe=None):
    return [entree["texte"] for entree in propositions(competence, classe)]
