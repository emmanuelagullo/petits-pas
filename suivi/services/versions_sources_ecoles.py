"""Identités de suivi par école ; aucune assimilation au code ou au libellé."""
from copy import deepcopy
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from suivi.identites_referentiels import identifiant_diffusion, reference_competence
from suivi.models import (Attendu, Competence, CompetenceLocale, CompetenceSourceEcole, Domaine, Ecole,
    FormulationProposee, SousDomaine, VersionSourceEcole)


@transaction.atomic
def definir_version_ecole(ecole, version):
    if version.source.ecole_id is not None:
        if version.source.ecole_id != ecole.pk:
            raise ValidationError("Cette version appartient à une autre école.")
        if version.contenu.get("origine") != "source_declaree":
            return deepcopy(version.contenu)
    if version.contenu.get("origine") != "source_declaree":
        raise ValidationError("La version n'est pas une source fournie déclarée.")
    Ecole.objects.select_for_update().get(pk=ecole.pk)
    existante = VersionSourceEcole.objects.filter(ecole=ecole, version=version).first()
    if existante:
        return deepcopy(existante.contenu)
    contenu = {"format": 1, "origine": "source_declaree", "source": deepcopy(version.contenu["source"]),
               "domaines": [], "sous_domaines": [], "attendus": [], "competences": [], "formulations": []}
    if version.contenu.get("structure_seule"):
        contenu["structure_seule"] = True
    identites = {
        reference_competence({"identite": i.identifiant, "source_origine":
                              "" if i.source_id == version.source_id else identifiant_diffusion(i.source)}): i
        for i in (d.identite for d in version.definitions.select_related("identite__source"))
    }

    def ajouter_competences(valeurs, domaine, sous_domaine=None):
        for c in valeurs:
            identite = identites[reference_competence(c)]
            liaison = CompetenceSourceEcole.objects.filter(ecole=ecole, identite=identite).first()
            if liaison is None:
                locale = None
                if identite.source.ecole_id == ecole.pk:
                    ajouts = CompetenceLocale.objects.filter(ecole=ecole, suivi_libre=False).select_related("competence")
                    if identite.identifiant.startswith("pp-"):
                        locale = ajouts.filter(definition__identite_portable=identite.identifiant).first()
                    elif (identite.identifiant.startswith("local-")
                          and identifiant_diffusion(identite.source) == f"ajout-{identite.identifiant}"):
                        locale = ajouts.filter(competence__code=identite.identifiant).first()
                competence = locale.competence if locale else Competence.objects.create(
                    domaine=domaine, sous_domaine=sous_domaine, code=c["code"],
                    libelle=c["libelle"], niveau=c["niveau"], icone=c["icone"])
                liaison = CompetenceSourceEcole(ecole=ecole, identite=identite, competence=competence)
                liaison.full_clean()
                liaison.save()
            competence = liaison.competence
            contenu["competences"].append({"id": competence.pk, "domaine_id": domaine.pk,
                "sous_domaine_id": sous_domaine.pk if sous_domaine else None, "code": c["code"],
                "libelle": c["libelle"], "niveau": c["niveau"], "icone": c["icone"], "active": True,
                "ordre": len(contenu["competences"]), "cle_definition": f"source-{identite.pk}"})
            if c.get("icone_png"):
                contenu["competences"][-1]["icone_png"] = c["icone_png"]
            for ordre, f in enumerate(c["formulations"]):
                base, _ = FormulationProposee.objects.get_or_create(competence=competence, code=f["code"],
                    defaults={"texte": f["texte"], "ordre": ordre})
                contenu["formulations"].append({"id": base.pk, "competence_id": competence.pk,
                    "code": f["code"], "texte": f["texte"], "ordre": ordre, "active": True})

    for ordre, d in enumerate(version.contenu["domaines"]):
        # Groupes propres à la version : aucun nom de domaine existant n'est réécrit.
        domaine = Domaine.objects.create(ecole=ecole, code="R" + uuid4().hex[:19], nom=d["nom"], ordre=ordre)
        contenu["domaines"].append({"id": domaine.pk, "code": d["code"], "nom": d["nom"], "ordre": ordre})
        for rang, a in enumerate(d["attendus"]):
            attendu = Attendu.objects.create(domaine=domaine, code=a["code"], texte=a["texte"], ordre=rang)
            contenu["attendus"].append({"id": attendu.pk, "domaine_id": domaine.pk, **a, "ordre": rang})
        ajouter_competences(d["competences"], domaine)
        for rang, s in enumerate(d["sous_domaines"]):
            sous = SousDomaine.objects.create(domaine=domaine, code=s["code"], nom=s["nom"], ordre=rang)
            contenu["sous_domaines"].append({"id": sous.pk, "domaine_id": domaine.pk,
                "code": s["code"], "nom": s["nom"], "ordre": rang})
            ajouter_competences(s["competences"], domaine, sous)
    projection = VersionSourceEcole(ecole=ecole, version=version, contenu=contenu)
    projection.full_clean()
    projection.save()
    return deepcopy(contenu)
