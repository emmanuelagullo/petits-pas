"""Lecture du référentiel commune aux saisies, réglages et carnets."""
from django.db.models import Case, IntegerField, Prefetch, Value, When

from .models import AdoptionReferentiel, Attendu, Competence, Domaine, SousDomaine


def adoption_courante(classe):
    if classe is None:
        return None
    if not hasattr(classe, "_adoption_referentiel_lecture"):
        classe._adoption_referentiel_lecture = AdoptionReferentiel.objects.filter(
            classe=classe, courante=True).select_related("version", "annuel").first()
    return classe._adoption_referentiel_lecture


def contenu_adoption(adoption):
    contenu = adoption.contenu or adoption.version.contenu
    return adoption.etat_final.get("contenu", contenu) if adoption.clos else contenu


def definition_classe(classe, competence):
    adoption = adoption_courante(classe)
    if adoption:
        contenu = contenu_adoption(adoption)
        if any(c["id"] == competence.pk for c in contenu.get("competences", [])):
            return contenu
        if not adoption.clos:
            for ancienne in adoptions_anterieures(classe, adoption):
                contenu = contenu_adoption(ancienne)
                if any(c["id"] == competence.pk for c in contenu.get("competences", [])):
                    return contenu
    return None


def adoptions_anterieures(classe, adoption):
    """D'abord les choix de cette classe, puis les parcours de l'école."""
    return AdoptionReferentiel.objects.filter(classe__ecole_id=classe.ecole_id,
        classe__annee_scolaire__lte=classe.annee_scolaire).exclude(pk=adoption.pk).select_related(
        "version").annotate(priorite=Case(When(classe=classe, then=Value(0)),
            default=Value(1), output_field=IntegerField())).order_by("priorite", "-classe__annee_scolaire", "-pk")


def arbre_version(ecole, contenu, *, niveaux=None, inclure_ids=(), masquer=True, masque_actuel=True):
    """Objets de lecture : aucune réécriture du catalogue ou de ses relations."""
    domaines = {}
    for ligne in contenu.get("domaines", []):
        domaine = Domaine(ecole=ecole, **ligne)
        domaine.visibles = []
        domaine._prefetched_objects_cache = {"attendus": []}
        domaines[domaine.pk] = domaine
    sous_domaines = {s["id"]: SousDomaine(**s) for s in contenu.get("sous_domaines", [])}
    for ligne in contenu.get("attendus", []):
        domaine = domaines.get(ligne["domaine_id"])
        if domaine:
            domaine._prefetched_objects_cache["attendus"].append(Attendu(**ligne))
    ids = [c["id"] for c in contenu.get("competences", [])]
    actuelles = Competence.objects.in_bulk(ids)
    for ligne in contenu.get("competences", []):
        actuelle = actuelles.get(ligne["id"])
        if actuelle is None:
            continue
        if niveaux and ligne["niveau"] not in niveaux:
            continue
        if masquer and (not ligne["active"] or (masque_actuel and not actuelle.active)) and ligne["id"] not in inclure_ids:
            continue
        competence = Competence(**{k: v for k, v in ligne.items() if k != "cle_definition"})
        competence._contenu_referentiel = contenu
        competence.domaine = domaines[ligne["domaine_id"]]
        competence.sous_domaine = sous_domaines.get(ligne["sous_domaine_id"])
        domaines[ligne["domaine_id"]].visibles.append(competence)
    for domaine in domaines.values():
        domaine.visibles.sort(key=lambda c: (c.ordre, c.pk))
    return sorted(domaines.values(), key=lambda d: (d.ordre, d.pk))


def arbre_competences(ecole, niveaux=None, *, classe=None, inclure_ids=()):
    if classe is not None and classe.ecole_id != ecole.pk:
        raise ValueError("Classe d'une autre école.")
    adoption = adoption_courante(classe)
    if adoption:
        contenu = contenu_adoption(adoption)
        arbre = arbre_version(ecole, contenu, niveaux=niveaux, inclure_ids=inclure_ids, masque_actuel=not adoption.clos)
        manquants = set(inclure_ids) - {c.pk for d in arbre for c in d.visibles}
        # Le parcours complet peut comporter des acquisitions d'une autre base
        # ou classe. Lire uniquement des définitions déjà adoptées dans l'école.
        if manquants and not adoption.clos:
            anciennes = adoptions_anterieures(classe, adoption)
            for ancienne in anciennes:
                groupes = arbre_version(ecole, contenu_adoption(ancienne), niveaux=niveaux,
                    inclure_ids=manquants, masquer=False, masque_actuel=False)
                for domaine in groupes:
                    domaine.visibles = [c for c in domaine.visibles if c.pk in manquants]
                    if domaine.visibles:
                        arbre.append(domaine)
                        manquants -= {c.pk for c in domaine.visibles}
                if not manquants:
                    break
        return arbre

    if classe is not None:
        from .models import SourceReferentiel
        initiale = SourceReferentiel.objects.filter(identifiant=f"reprise-ecole-{ecole.pk}", ecole=ecole).first()
        if initiale:
            from .services.choix_bases_referentiels import choix_bases
            choix = choix_bases(ecole, classe.annee_scolaire)
            # Une lecture ne matérialise pas une source et ne crée pas une adoption.
            if choix.proposee and choix.proposee.source_id == initiale.pk:
                return arbre_version(ecole, choix.proposee.contenu, niveaux=niveaux, inclure_ids=inclure_ids)
            return []

    competences = ((Competence.objects.filter(active=True) | Competence.objects.filter(pk__in=inclure_ids))
                   .select_related("sous_domaine", "domaine__ecole")
                   .order_by("ordre", "pk"))
    if niveaux:
        competences = competences.filter(niveau__in=niveaux)
    return Domaine.objects.filter(ecole=ecole).order_by("ordre", "pk").prefetch_related(
        Prefetch("competences", queryset=competences, to_attr="visibles"),
        "attendus",
    )


def observations_annee(eleve, scolarite):
    """Projection de lecture, sans emprunter un état courant à une autre année."""
    from copy import copy
    from django.db.models import Q
    from .models import EtatAnnuelObservation, Trace

    annuels = {e.observation_id: e for e in EtatAnnuelObservation.objects.filter(
        observation__eleve=eleve, annee_scolaire=scolarite.annee_scolaire)}
    adoption = adoption_courante(scolarite.classe)
    if adoption and adoption.clos and "etats" in adoption.etat_final:
        from datetime import date
        from types import SimpleNamespace
        annuels = {e["observation_id"]: SimpleNamespace(
            statut=e["statut"], connu=e["connu"],
            date_observation=date.fromisoformat(e["date_observation"]) if e["date_observation"] else None)
            for e in adoption.etat_final["etats"]}
    traces = list(Trace.objects.filter(scolarite=scolarite, observation__eleve=eleve,
                                      visible_carnet=True, supprime_le__isnull=True))
    par_observation = {}
    for trace in traces:
        par_observation.setdefault(trace.observation_id, []).append(trace)
    observations = eleve.observations.filter(Q(pk__in=annuels) | Q(pk__in=par_observation)).select_related("competence")
    etats = {}
    inconnus = False
    for observation in observations:
        copie = copy(observation)
        annuel = annuels.get(observation.pk)
        copie.traces_carnet = par_observation.get(observation.pk, [])
        copie.historique_inconnu = annuel is None or not annuel.connu
        inconnus = inconnus or copie.historique_inconnu
        copie.statut = annuel.statut if annuel and annuel.connu else None
        copie.date_observation = (annuel.date_observation if annuel and annuel.connu else
                                  max((t.date_observation for t in copie.traces_carnet), default=None))
        copie.annee_historique = scolarite.annee_scolaire
        etats[copie.competence_id] = copie
    return etats, inconnus


def competence_classe(classe, competence):
    for domaine in arbre_competences(classe.ecole, classe=classe, inclure_ids=[competence.pk]):
        for candidate in domaine.visibles:
            if candidate.pk == competence.pk:
                return candidate
    return None


def classe_historique(classe):
    # Une date civile ne clôture pas une classe implicitement.
    adoption = adoption_courante(classe)
    return bool(adoption and adoption.clos)


def observations_classe(classe):
    """États de lecture SQL ; les comptages ne chargent pas les traces/photos."""
    from datetime import date
    from django.db.models import BooleanField, Case, CharField, DateField, Exists, F, OuterRef, Subquery, Value, When
    from .models import EtatAnnuelObservation, Observation, Scolarite
    queryset = Observation.objects.filter(eleve__scolarites__classe=classe, eleve__ecole_id=classe.ecole_id,
                                          competence__domaine__ecole_id=classe.ecole_id)
    adoption = adoption_courante(classe)
    if adoption is None:
        return queryset.annotate(statut_lecture=F("statut"), connu_lecture=Value(True), date_lecture=F("date_observation"))
    if adoption.clos and "etats" in adoption.etat_final:
        etats = adoption.etat_final["etats"]
        return queryset.annotate(
            statut_lecture=Case(*[When(pk=e["observation_id"], then=Value(e["statut"])) for e in etats if e["connu"]],
                                default=Value(None), output_field=CharField()),
            connu_lecture=Case(*[When(pk=e["observation_id"], then=Value(e["connu"])) for e in etats],
                               default=Value(False), output_field=BooleanField()),
            date_lecture=Case(*[When(pk=e["observation_id"], then=Value(date.fromisoformat(e["date_observation"])))
                               for e in etats if e["connu"] and e["date_observation"]],
                              default=Value(None), output_field=DateField()))
    annuels = EtatAnnuelObservation.objects.filter(observation_id=OuterRef("pk"), annee_scolaire=classe.annee_scolaire, connu=True)
    plus_recent = Scolarite.objects.filter(eleve_id=OuterRef("eleve_id"), annee_scolaire__gt=classe.annee_scolaire)
    return queryset.annotate(autre_annee=Exists(plus_recent),
        statut_ancien=Subquery(annuels.values("statut")[:1]),
        connu_ancien=Subquery(annuels.values("connu")[:1]),
        date_ancienne=Subquery(annuels.values("date_observation")[:1])).annotate(
            statut_lecture=Case(When(autre_annee=True, then=F("statut_ancien")), default=F("statut")),
            connu_lecture=Case(When(autre_annee=True, then=F("connu_ancien")), default=Value(True), output_field=BooleanField()),
            date_lecture=Case(When(autre_annee=True, then=F("date_ancienne")), default=F("date_observation")))


def projeter_etat_classe(observation):
    observation.statut = observation.statut_lecture
    observation.date_observation = observation.date_lecture
    observation.historique_inconnu = not observation.connu_lecture
    return observation
