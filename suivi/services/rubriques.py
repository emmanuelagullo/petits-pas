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
    if any(d["id"] != rubrique_id and (not sous or d["domaine_id"] == domaine_id)
           and d["nom"].casefold() == nom.casefold() for d in choix.values()):
        raise ValidationError("Une rubrique porte déjà ce nom à cet emplacement.")
    if existante is None:
        code = f"local-{uuid4().hex[:14]}"
        if sous:
            rubrique_id = SousDomaine.objects.create(domaine_id=domaine_id, code=code, nom=nom, ordre=ordre).pk
        else:
            rubrique_id = Domaine.objects.create(ecole=classe.ecole, code=code, nom=nom, ordre=ordre).pk
    regle, _ = RubriqueClasse.objects.update_or_create(
        classe=classe, domaine_id=domaine_id if sous else rubrique_id,
        sous_domaine_id=rubrique_id if sous else None,
        defaults={"nom": nom, "ordre": ordre, "masquee": masquee},
        create_defaults={"nom": nom, "ordre": ordre, "masquee": masquee, "creee": existante is None},
    )
    journaliser(utilisateur, "referentiel.rubrique_enregistree", regle,
                nouvelles={"nom": nom, "ordre": ordre, "masquee": masquee})
