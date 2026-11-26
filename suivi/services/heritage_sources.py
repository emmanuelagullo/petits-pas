"""Propositions des éditions suivies pour les compétences déjà présentes."""
from suivi.identites_referentiels import est_uuid_portable, identifiant_diffusion
from suivi.models import AdaptationCompetence, AdoptionReferentiel, CompetenceSourceEcole, FormulationProposee, SuiviSourceClasse, VersionReferentiel
from .apercu_mises_a_jour import definitions_document

CHAMPS = {"libelle": "Libellé", "illustration": "Illustration", "niveau": "Section",
          "formulations": "Phrases proposées", "active": "Disponibilité à la saisie"}


def propositions_suivies(classe, ids=None):
    suivis = {int(s.reference[7:]): s for s in SuiviSourceClasse.objects.filter(classe=classe)
              if s.reference.startswith("source-") and s.reference[7:].isdigit()}
    if ids == []:
        return {}
    emprunts = AdaptationCompetence.objects.filter(classe=classe, annee_scolaire=classe.annee_scolaire
                                                 ).exclude(source_heritage="")
    if ids is not None:
        emprunts = emprunts.filter(competence_id__in=ids)
    origines = dict(emprunts.values_list("competence_id", "source_heritage"))
    if not suivis and not origines:
        return {}
    liaisons = CompetenceSourceEcole.objects.filter(ecole=classe.ecole, identite__identifiant__startswith="pp-")
    if ids is not None:
        liaisons = liaisons.filter(competence_id__in=ids)
    competences = {uuid: pk for uuid, pk in liaisons.values_list("identite__identifiant", "competence_id")
                   if est_uuid_portable(uuid)}
    from django.db.models import Q

    sources = Q(source_id__in=suivis) | Q(source__ecole=classe.ecole, source__identifiant_diffusion__in=origines.values())
    sources |= Q(source__ecole__isnull=True, source__identifiant__in=origines.values())
    versions = {}
    for version in VersionReferentiel.objects.filter(sources, Q(source__classe_privee__isnull=True) | Q(source__classe_privee=classe),
            contenu__origine="source_declaree").select_related("source").order_by("-pk"):
        versions.setdefault(version.source_id, version)
    resultat = {}
    for source_id, version in versions.items():
        if version.source.ecole_id not in (None, classe.ecole_id):
            continue
        suivi = suivis.get(source_id)
        for uuid, definition in definitions_document(version.contenu).items():
            pk = competences.get(uuid)
            origine_reprise = origines.get(pk) == identifiant_diffusion(version.source)
            if pk is None or (not suivi and not origine_reprise):
                continue
            champs = {"libelle": definition["libelle"], "niveau": definition["niveau"],
                      "formulations": definition["formulations"],
                      "illustration": [definition.get("icone", ""), definition.get("icone_png", "")]}
            if "active" in definition:
                champs["active"] = definition["active"]
            for champ, valeur in champs.items():
                resultat.setdefault(pk, {}).setdefault(champ, []).append({
                    "source": source_id, "titre": version.source.titre, "edition": version.numero,
                    "libelle_competence": definition["libelle"], "valeur": valeur, "choisie": bool(suivi and champ in suivi.champs_herites.get(uuid, ())),
                    "origine_reprise": origine_reprise, "uuid": uuid,
                })
    autres = {int(cle[7:]) for cle in origines.values()
              if cle.startswith("classe:") and cle[7:].isdecimal()}
    if autres:
        from .partage_referentiel_classe import contenu_commun_classe

        for adoption in AdoptionReferentiel.objects.filter(
            classe_id__in=autres, classe__ecole=classe.ecole, classe__etat=classe.ACTIVE,
            classe__annee_scolaire__lte=classe.annee_scolaire, courante=True, clos=False,
        ).select_related("classe", "version"):
            contenu = contenu_commun_classe(adoption, avec_heritage=False)
            for definition in contenu["competences"]:
                pk = definition["id"]
                if origines.get(pk) != f"classe:{adoption.classe_id}":
                    continue
                champs = {"libelle": definition["libelle"], "niveau": definition["niveau"],
                          "illustration": [definition.get("icone", ""), definition.get("icone_png", "")],
                          "formulations": [{"code": f["code"], "texte": f["texte"]}
                                           for f in contenu.get("formulations", [])
                                           if f["competence_id"] == pk and f["active"]]}
                for champ, valeur in champs.items():
                    resultat.setdefault(pk, {}).setdefault(champ, []).append({
                        "source": None, "titre": adoption.classe.nom, "edition": "contenu courant",
                        "libelle_competence": definition["libelle"], "valeur": valeur,
                        "choisie": False, "origine_reprise": True, "uuid": f"classe:{pk}",
                    })
    return resultat


def valeur_heritee(propositions):
    choisies = [c for c in propositions if c["choisie"]]
    candidates = choisies or [c for c in propositions if c["origine_reprise"]] or propositions
    valeur = candidates[0]["valeur"]
    return valeur if all(c["valeur"] == valeur for c in candidates) else None


def appliquer_heritage(classe, contenu, principale):
    definitions = [c for c in contenu.get("competences", []) if c["id"] not in principale]
    propositions = propositions_suivies(classe, [c["id"] for c in definitions])
    if not propositions:
        return
    from suivi.models import CompetenceLocale

    memoire = {}
    for suivi in SuiviSourceClasse.objects.filter(classe=classe).only("memoire_heritage"):
        for uuid, champs in suivi.memoire_heritage.items():
            for champ, valeur in champs.items():
                cle = (uuid, champ)
                if cle not in memoire or memoire[cle]["date"] < valeur["date"]:
                    memoire[cle] = valeur
    locales = set(CompetenceLocale.objects.filter(competence_id__in=propositions)
                  .values_list("competence_id", flat=True))
    for definition in definitions:
        for champ, choix in propositions.get(definition["id"], {}).items():
            if definition["id"] in locales and not any(c["choisie"] or c["origine_reprise"] for c in choix):
                continue
            valeur = valeur_heritee(choix)
            if valeur is None:
                valeur = memoire.get((choix[0]["uuid"], champ), {}).get("valeur")
            if valeur is None:
                continue
            if champ in ("libelle", "niveau", "active"):
                definition[champ] = valeur
            elif champ == "formulations":
                pk = definition["id"]
                existantes = {f.code: f.pk for f in FormulationProposee.objects.filter(competence_id=pk)}
                if all(f["code"] in existantes for f in valeur):
                    contenu["formulations"] = [
                        f for f in contenu.get("formulations", []) if f["competence_id"] != pk
                    ] + [{**f, "id": existantes[f["code"]], "competence_id": pk,
                          "ordre": ordre, "active": True} for ordre, f in enumerate(valeur)]
            else:
                definition["icone"], png = valeur
                if png:
                    definition["icone_png"] = png
                else:
                    definition.pop("icone_png", None)


def memoriser_avant_nouvelle_edition(source):
    """Préserver la dernière valeur commune avant qu’une édition puisse la contredire."""
    from django.utils import timezone

    from suivi.models import CompetenceLocale
    from suivi.referentiels import adoption_courante, contenu_origine

    suivis = SuiviSourceClasse.objects.select_for_update().filter(
        reference=f"source-{source.pk}",
    ).select_related("classe__ecole").order_by("pk")
    date = timezone.now().isoformat()
    for suivi in suivis:
        adoption = adoption_courante(suivi.classe)
        if not adoption or adoption.clos:
            continue
        principale = {c["id"] for c in contenu_origine(adoption).get("competences", [])}
        propositions = propositions_suivies(suivi.classe)
        locales = set(CompetenceLocale.objects.filter(competence_id__in=propositions)
                      .values_list("competence_id", flat=True))
        modifie = False
        for pk, champs in propositions.items():
            if pk in principale:
                continue
            for champ, candidats in champs.items():
                if pk in locales and not any(c["choisie"] for c in candidats):
                    continue
                if not any(c["source"] == source.pk for c in candidats):
                    continue
                valeur = valeur_heritee(candidats)
                if valeur is not None:
                    suivi.memoire_heritage.setdefault(candidats[0]["uuid"], {})[champ] = {
                        "date": date, "valeur": valeur,
                    }
                    modifie = True
        if modifie:
            suivi.save(update_fields=["memoire_heritage"])

def preparer_phrases_heritees(version):
    definitions = definitions_document(version.contenu)
    liaisons = CompetenceSourceEcole.objects.filter(
        identite__definitions__version=version, identite__identifiant__startswith="pp-",
    ).values_list("identite__identifiant", "competence_id")
    for uuid, pk in liaisons:
        if est_uuid_portable(uuid):
            for ordre, phrase in enumerate(definitions[uuid]["formulations"]):
                FormulationProposee.objects.get_or_create(
                    competence_id=pk, code=phrase["code"], defaults={"texte": phrase["texte"], "ordre": ordre},
                )
