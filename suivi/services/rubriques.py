"""Modification locale des rubriques, sous le verrou du référentiel de classe."""
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from suivi.audit import journaliser
from suivi.models import Domaine, RubriqueClasse, SousDomaine
from suivi.referentiels import contenu_adoption
from .ajouts_referentiels import _verrouiller


@transaction.atomic
def enregistrer_rubrique(utilisateur, classe, *, adoption_id, genre, domaine_id, rubrique_id, nom, ordre, masquee):
    adoption = _verrouiller(utilisateur, classe.ecole, classe.annee_scolaire, classe, adoption_id)
    contenu = contenu_adoption(adoption)
    domaines = {d["id"]: d for d in contenu["domaines"]}
    groupes = {s["id"]: s for s in contenu["sous_domaines"]}
    sous = genre == "sous_domaine"
    if sous and domaine_id not in domaines:
        raise ValidationError("Choisissez une rubrique de cette classe.")
    choix = groupes if sous else domaines
    existante = choix.get(rubrique_id)
    if rubrique_id is not None and (existante is None or (sous and existante["domaine_id"] != domaine_id)):
        raise ValidationError("Cette rubrique n’appartient pas à cet emplacement.")
    if nom is None:
        if existante is None:
            raise ValidationError("Choisissez une rubrique existante.")
        nom = existante["nom"]
    if any(d["id"] != rubrique_id and (not sous or d["domaine_id"] == domaine_id)
           and d["nom"].casefold() == nom.casefold() for d in choix.values()):
        raise ValidationError("Une rubrique porte déjà ce nom à cet emplacement.")
    if ordre is None:
        ordre = (existante["ordre"] if existante else min(32767, 1 + max(
            (d["ordre"] for d in choix.values() if not sous or d["domaine_id"] == domaine_id), default=-1)))
    if existante is None:
        code = f"local-{uuid4().hex[:14]}"
        if sous:
            rubrique_id = SousDomaine.objects.create(domaine_id=domaine_id, code=code, nom=nom, ordre=ordre).pk
        else:
            rubrique_id = Domaine.objects.create(ecole=classe.ecole, code=code, nom=nom, ordre=ordre).pk
    valeurs = {"nom": nom, "ordre": ordre}
    if masquee is not None:
        valeurs["masquee"] = masquee
    regle, _ = RubriqueClasse.objects.update_or_create(
        classe=classe, domaine_id=domaine_id if sous else rubrique_id,
        sous_domaine_id=rubrique_id if sous else None,
        defaults=valeurs,
        create_defaults={**valeurs, "creee": existante is None},
    )
    journaliser(utilisateur, "referentiel.rubrique_enregistree", regle,
                nouvelles={"nom": nom, "ordre": ordre, "masquee": regle.masquee})


@transaction.atomic
def deplacer_rubrique(utilisateur, classe, *, adoption_id, genre, domaine_id, rubrique_id,
                     ordre_initial, action, cible_id=None, apres=False):
    adoption = _verrouiller(utilisateur, classe.ecole, classe.annee_scolaire, classe, adoption_id)
    contenu = contenu_adoption(adoption)
    sous = genre == "sous_domaine"
    lignes = ([s for s in contenu["sous_domaines"] if s["domaine_id"] == domaine_id]
              if sous else contenu["domaines"])
    ordre = [r["id"] for r in lignes]
    if ordre != ordre_initial or rubrique_id not in ordre:
        raise ValidationError("L’ordre a changé. Rechargez la liste avant de recommencer.")
    origine = ordre.index(rubrique_id)
    if action == "glisser":
        if cible_id not in ordre or cible_id == rubrique_id:
            raise ValidationError("Choisissez une destination au même niveau.")
        ordre.remove(rubrique_id)
        ordre.insert(ordre.index(cible_id) + int(apres), rubrique_id)
    else:
        destination = origine + (-1 if action == "monter" else 1)
        if not 0 <= destination < len(ordre):
            return
        ordre[origine], ordre[destination] = ordre[destination], ordre[origine]
    par_id = {r["id"]: r for r in lignes}
    for position, identifiant in enumerate(ordre, 1):
        ligne = par_id[identifiant]
        if ligne["ordre"] != position:
            RubriqueClasse.objects.update_or_create(
                classe=classe, domaine_id=domaine_id if sous else identifiant,
                sous_domaine_id=identifiant if sous else None,
                defaults={"ordre": position},
                create_defaults={"ordre": position, "nom": ligne["nom"]},
            )
    journaliser(utilisateur, "referentiel.rubriques_reordonnees", classe,
                anciennes={"ordre": ordre_initial}, nouvelles={"ordre": ordre, "domaine": domaine_id})
