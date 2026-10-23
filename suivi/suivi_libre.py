"""Lecture de la portée ; aucune attribution ni acquisition implicite."""
from django.core.exceptions import PermissionDenied
from .models import CompetenceLocale, EleveApprentissage


def est_libre(competence):
    return CompetenceLocale.objects.filter(competence_id=competence.pk, suivi_libre=True).exists()


def eleves_suivis(classe, competence, *, actifs=True):
    q = EleveApprentissage.objects.filter(disponibilite__classe=classe,
        disponibilite__locale__competence_id=competence.pk,
        disponibilite__annee_scolaire=classe.annee_scolaire)
    if actifs:
        q = q.filter(active=True)
    return set(q.values_list("scolarite__eleve_id", flat=True))


def verifier_portee(classe, competence, *, eleve=None):
    if est_libre(competence) and eleve is not None and eleve.pk not in eleves_suivis(classe, competence):
        raise PermissionDenied("Cet apprentissage n’est pas proposé à cet élève.")


def filtrer_arbre(arbre, classe, eleve):
    """Le lecteur commun fournit les définitions ; seule la portée est filtrée."""
    libres = set(CompetenceLocale.objects.filter(ecole=classe.ecole, suivi_libre=True)
                 .values_list("competence_id", flat=True))
    admis = set(EleveApprentissage.objects.filter(disponibilite__classe=classe,
        scolarite__eleve=eleve).values_list("disponibilite__locale__competence_id", flat=True))
    # Conserver l’historique même après retrait des prochaines saisies.
    admis.update(eleve.observations.values_list("competence_id", flat=True))
    for domaine in arbre:
        domaine.visibles = [c for c in domaine.visibles if c.pk not in libres or c.pk in admis]
    return arbre


def preparer_arbre(arbre, classe, eleve=None):
    if classe is None:
        return arbre
    locales = {c.competence_id: c.pk for c in CompetenceLocale.objects.filter(
        ecole=classe.ecole, suivi_libre=True)}
    liens = list(EleveApprentissage.objects.filter(disponibilite__classe=classe).values_list(
        "disponibilite__locale__competence_id", "scolarite__eleve_id", "active"))
    admis, actifs = {}, {}
    for cid, eid, active in liens:
        admis.setdefault(cid, set()).add(eid)
        if active:
            actifs.setdefault(cid, set()).add(eid)
    historiques = set(eleve.observations.values_list("competence_id", flat=True)) if eleve else set()
    for d in arbre:
        if eleve:
            d.visibles = [c for c in d.visibles if c.pk not in locales
                          or eleve.pk in admis.get(c.pk, set()) or c.pk in historiques]
        for c in d.visibles:
            c.suivi_libre = c.pk in locales
            c.libre_id = locales.get(c.pk)
            c.eleves_suivis_ids = actifs.get(c.pk, set())
            c.nombre_suivis = len(c.eleves_suivis_ids)
            c.saisie_ouverte = not (c.suivi_libre and eleve and eleve.pk not in c.eleves_suivis_ids)
    return arbre
