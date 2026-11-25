"""Propositions des éditions suivies pour les compétences déjà présentes."""
from suivi.identites_referentiels import est_uuid_portable
from suivi.models import CompetenceSourceEcole, SuiviSourceClasse, VersionReferentiel
from .apercu_mises_a_jour import definitions_document

CHAMPS = {"libelle": "Libellé", "illustration": "Illustration"}


def propositions_suivies(classe, ids=None):
    suivis = {int(s.reference[7:]): s for s in SuiviSourceClasse.objects.filter(classe=classe)
              if s.reference.startswith("source-") and s.reference[7:].isdigit()}
    if not suivis or ids == []:
        return {}
    liaisons = CompetenceSourceEcole.objects.filter(ecole=classe.ecole, identite__identifiant__startswith="pp-")
    if ids is not None:
        liaisons = liaisons.filter(competence_id__in=ids)
    competences = {uuid: pk for uuid, pk in liaisons.values_list("identite__identifiant", "competence_id")
                   if est_uuid_portable(uuid)}
    versions = {}
    for version in VersionReferentiel.objects.filter(source_id__in=suivis,
            contenu__origine="source_declaree").select_related("source").order_by("-pk"):
        versions.setdefault(version.source_id, version)
    resultat = {}
    for source_id, version in versions.items():
        if version.source.ecole_id not in (None, classe.ecole_id):
            continue
        suivi = suivis[source_id]
        for uuid, definition in definitions_document(version.contenu).items():
            pk = competences.get(uuid)
            if pk is None:
                continue
            champs = {"libelle": definition["libelle"],
                      "illustration": [definition.get("icone", ""), definition.get("icone_png", "")]}
            for champ, valeur in champs.items():
                resultat.setdefault(pk, {}).setdefault(champ, []).append({
                    "source": source_id, "titre": version.source.titre, "edition": version.numero,
                    "libelle_competence": definition["libelle"], "valeur": valeur, "choisie": champ in suivi.champs_herites.get(uuid, ()), "uuid": uuid,
                })
    return resultat


def valeur_heritee(propositions):
    choisies = [c for c in propositions if c["choisie"]]
    candidates = choisies or propositions
    valeur = candidates[0]["valeur"]
    return valeur if all(c["valeur"] == valeur for c in candidates) else None


def appliquer_heritage(classe, contenu, principale):
    definitions = [c for c in contenu.get("competences", []) if c["id"] not in principale]
    propositions = propositions_suivies(classe, [c["id"] for c in definitions])
    if not propositions:
        return
    from suivi.models import CompetenceLocale

    locales = set(CompetenceLocale.objects.filter(competence_id__in=propositions)
                  .values_list("competence_id", flat=True))
    for definition in definitions:
        for champ, choix in propositions.get(definition["id"], {}).items():
            if definition["id"] in locales and not any(c["choisie"] for c in choix):
                continue
            valeur = valeur_heritee(choix)
            if valeur is None:
                continue
            if champ == "libelle":
                definition["libelle"] = valeur
            else:
                definition["icone"], png = valeur
                if png:
                    definition["icone_png"] = png
                else:
                    definition.pop("icone_png", None)
