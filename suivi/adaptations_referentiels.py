"""Lecture des libellés et masquages ; aucune réécriture des sources."""
from copy import deepcopy

from django.db.models import Q

from .models import AdaptationCompetence, AdoptionReferentiel, Competence, VersionReferentiel, VersionSourceEcole


def contenu_adapte(ecole, annee, contenu, classe=None):
    resultat = deepcopy(contenu)
    ids = [c["id"] for c in resultat.get("competences", [])]
    actuelles = Competence.objects.in_bulk(ids)
    filtres = Q(classe__isnull=True)
    if classe is not None:
        filtres |= Q(classe=classe)
    regles = list(AdaptationCompetence.objects.filter(filtres, ecole=ecole,
        annee_scolaire=annee, competence_id__in=ids).order_by("classe_id", "pk"))
    # L'ordre des valeurs NULL dépend du moteur ; appliquer les deux niveaux
    # explicitement plutôt que compter sur le tri SQL.
    regles.sort(key=lambda r: r.classe_id is not None)
    par_competence = {}
    for regle in regles:
        par_competence.setdefault(regle.competence_id, []).append(regle)
    for definition in resultat.get("competences", []):
        actuelle = actuelles.get(definition["id"])
        definition["active"] = definition["active"] and bool(actuelle and actuelle.active)
        for regle in par_competence.get(definition["id"], []):
            if regle.libelle is not None:
                definition["libelle"] = regle.libelle
            if regle.visible is not None:
                definition["active"] = regle.visible
    return resultat


def contenus_ecole(ecole, annee):
    """Bases utilisées dans l'année ou déjà préparées ; aucune matérialisation."""
    from .referentiels import contenu_origine
    from .services.choix_bases_referentiels import choix_bases
    contenus = {}
    for adoption in AdoptionReferentiel.objects.filter(classe__ecole=ecole,
        classe__annee_scolaire=annee).select_related("version__source").order_by("-pk"):
        contenus.setdefault(adoption.version_id, (adoption.version, contenu_origine(adoption)))
    choix = choix_bases(ecole, annee)
    for preparation in VersionSourceEcole.objects.filter(ecole=ecole,
        version_id__in=[v.pk for v in choix.versions]).select_related("version__source"):
        contenus.setdefault(preparation.version_id, (preparation.version, preparation.contenu))
    initiale = VersionReferentiel.objects.filter(source__ecole=ecole,
        source__identifiant=f"reprise-ecole-{ecole.pk}", numero="initial").select_related("source").first()
    if initiale:
        contenus.setdefault(initiale.pk, (initiale, initiale.contenu))
    return sorted(contenus.values(), key=lambda paire: (paire[0].source.titre, paire[0].pk))
