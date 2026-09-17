from functools import wraps

from django.contrib import messages
from django.db import DatabaseError, connection
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe

from .models import Classe, Competence, Domaine, Ecole, Eleve, Observation


# --------------------------------------------------------------------------
# Accès
# --------------------------------------------------------------------------


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})


def acces_requis(vue):
    @wraps(vue)
    def _vue(request, *args, **kwargs):
        if not request.session.get("ecole_id"):
            request.session["suivant"] = request.get_full_path()
            return redirect("connexion")
        return vue(request, *args, **kwargs)

    return _vue


def direction_requise(vue):
    @wraps(vue)
    @acces_requis
    def _vue(request, *args, **kwargs):
        if request.session.get("role") != "direction":
            return HttpResponseForbidden(
                "Cette page est réservée au mot de passe de direction."
            )
        return vue(request, *args, **kwargs)

    return _vue


def ecole_courante(request):
    return get_object_or_404(Ecole, pk=request.session["ecole_id"])


def connexion(request):
    if request.method == "POST":
        saisi = request.POST.get("mot_de_passe", "")
        for ecole in Ecole.objects.all():
            role = ecole.verifier(saisi)
            if role:
                request.session["ecole_id"] = ecole.pk
                request.session["role"] = role
                return redirect(request.session.pop("suivant", None) or "accueil")
        messages.error(
            request, "Ce mot de passe ne correspond à aucune école. Vérifiez la casse."
        )
    return render(request, "suivi/connexion.html")


def deconnexion(request):
    request.session.flush()
    return redirect("connexion")


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------


@acces_requis
def accueil(request):
    ecole = ecole_courante(request)
    classes = ecole.classes.annotate(nb_eleves=Count("eleves"))
    return render(request, "suivi/accueil.html", {"classes": classes})


def _progression(eleves, ecole):
    """Nombre de compétences réussies par élève, en un seul aller-retour."""
    total = Competence.objects.filter(domaine__ecole=ecole, active=True).count()
    compte = dict(
        Eleve.objects.filter(pk__in=[e.pk for e in eleves])
        .annotate(n=Count("observations", filter=Q(observations__statut="reussi")))
        .values_list("pk", "n")
    )
    for e in eleves:
        e.nb_reussies = compte.get(e.pk, 0)
        e.part_reussies = round(100 * e.nb_reussies / total) if total else 0
    return total


@acces_requis
def classe_detail(request, pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    eleves = list(classe.eleves.all())
    total = _progression(eleves, ecole)
    return render(
        request,
        "suivi/classe.html",
        {"classe": classe, "eleves": eleves, "total_competences": total},
    )


# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------


def _arbre(ecole, niveaux=None):
    competences = Competence.objects.filter(active=True)
    if niveaux:
        competences = competences.filter(niveau__in=niveaux)
    return Domaine.objects.filter(ecole=ecole).prefetch_related(
        Prefetch("competences", queryset=competences, to_attr="visibles")
    )


@acces_requis
def saisie_eleve(request, pk):
    """L'écran du quotidien : un enfant, tout ce qu'il sait faire."""
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, classe__ecole=ecole)
    filtre = request.GET.get("niveaux", "tous")
    niveaux = None if filtre == "tous" else [filtre]

    etats = {o.competence_id: o for o in eleve.observations.all()}
    domaines = []
    for d in _arbre(ecole, niveaux):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles]
        if lignes:
            domaines.append((d, lignes))

    return render(
        request,
        "suivi/saisie_eleve.html",
        {"eleve": eleve, "domaines": domaines, "filtre": filtre},
    )


@acces_requis
def choisir_competence(request, pk):
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    domaines = [(d, d.visibles) for d in _arbre(ecole) if d.visibles]
    return render(
        request,
        "suivi/choisir_competence.html",
        {"classe": classe, "domaines": domaines},
    )


@acces_requis
def saisie_competence(request, pk, competence_pk):
    """La saisie éclair : une compétence, toute la classe d'un coup."""
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    etats = {
        o.eleve_id: o
        for o in Observation.objects.filter(
            competence=competence, eleve__classe=classe
        )
    }
    lignes = [(e, etats.get(e.pk)) for e in classe.eleves.all()]
    return render(
        request,
        "suivi/saisie_competence.html",
        {"classe": classe, "competence": competence, "lignes": lignes},
    )


SUITE = {
    None: Observation.REUSSI,
    Observation.REUSSI: Observation.EN_COURS,
    Observation.EN_COURS: Observation.NON_DEBUTE,
    Observation.NON_DEBUTE: Observation.REUSSI,
}


@acces_requis
def basculer(request, eleve_pk, competence_pk):
    """Un clic fait avancer l'état : rien → réussi → en cours → rien."""
    if request.method != "POST":
        return HttpResponseForbidden("POST attendu.")
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=eleve_pk, classe__ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)

    obs = Observation.objects.filter(
        eleve=eleve,
        competence=competence,
    ).first()

    suivant = SUITE[obs.statut if obs else None]

    if obs is None:
        obs = Observation.objects.create(
            eleve=eleve,
            competence=competence,
            statut=suivant,
        )
    else:
        obs.statut = suivant
        obs.date_observation = timezone.localdate()
        obs.save(update_fields=["statut", "date_observation", "modifie_le"])

    gabarit = (
        "suivi/partiels/case_eleve.html"
        if request.GET.get("vue") == "classe"
        else "suivi/partiels/case_competence.html"
    )
    return render(
        request,
        gabarit,
        {"eleve": eleve, "competence": competence, "obs": obs},
    )


@acces_requis
def trace(request, eleve_pk, competence_pk):
    """Ajouter un commentaire ou une photo à une réussite."""
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=eleve_pk, classe__ecole=ecole)
    competence = get_object_or_404(Competence, pk=competence_pk, domaine__ecole=ecole)
    obs, _ = Observation.objects.get_or_create(eleve=eleve, competence=competence)

    if request.method == "POST":
        obs.commentaire = request.POST.get("commentaire", "").strip()
        if request.POST.get("retirer_photo"):
            obs.photo = None
        if request.FILES.get("photo"):
            obs.photo = request.FILES["photo"]
        date = request.POST.get("date_observation")
        if date:
            obs.date_observation = date
        obs.save()
        messages.success(request, f"Trace enregistrée pour {eleve.prenom}.")
        return redirect(reverse("saisie_eleve", args=[eleve.pk]) + f"#c{competence.pk}")

    return render(
        request,
        "suivi/trace.html",
        {"eleve": eleve, "competence": competence, "obs": obs},
    )


# --------------------------------------------------------------------------
# Carnet
# --------------------------------------------------------------------------


@acces_requis
def carnet(request, pk):
    ecole = ecole_courante(request)
    eleve = get_object_or_404(Eleve, pk=pk, classe__ecole=ecole)
    modes = {"reussites", "observes", "tout"}
    mode = request.GET.get("contenu", "observes")
    colonnes = request.GET.get("colonnes", "2")
    # Compatibilité avec les liens de la version 0.2.
    if request.GET.get("tout") == "1":
        mode = "tout"
    if mode not in modes:
        mode = "observes"
    if colonnes not in {"1", "2"}:
        colonnes = "2"

    etats = {o.competence_id: o for o in eleve.observations.select_related("competence")}
    domaines = []
    for d in _arbre(ecole):
        lignes = [(c, etats.get(c.pk)) for c in d.visibles]
        if mode == "reussites":
            lignes = [
                (c, o) for c, o in lignes if o and o.statut == Observation.REUSSI
            ]
        elif mode == "observes":
            lignes = [
                (c, o)
                for c, o in lignes
                if o and o.statut in (Observation.REUSSI, Observation.EN_COURS)
            ]
        if lignes:
            domaines.append((d, lignes))

    return render(
        request,
        "suivi/carnet.html",
        {
            "eleve": eleve,
            "domaines": domaines,
            "mode": mode,
            "colonnes": colonnes,
            "edite_le": timezone.localdate(),
        },
    )


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------


@direction_requise
def gestion(request):
    ecole = ecole_courante(request)
    classes = ecole.classes.annotate(nb_eleves=Count("eleves"))
    nb_competences = Competence.objects.filter(domaine__ecole=ecole, active=True).count()
    return render(
        request,
        "suivi/gestion.html",
        {"classes": classes, "nb_competences": nb_competences},
    )


@direction_requise
def creer_classe(request):
    ecole = ecole_courante(request)
    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        if nom:
            classe = Classe.objects.create(ecole=ecole, nom=nom)
            return redirect("importer_eleves", pk=classe.pk)
        messages.error(request, "Donnez un nom à la classe.")
    return render(request, "suivi/creer_classe.html")


@direction_requise
def importer_eleves(request, pk):
    """Coller la liste de la classe, un enfant par ligne."""
    ecole = ecole_courante(request)
    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)

    if request.method == "POST":
        niveau_defaut = request.POST.get("niveau", "PS")
        ajoutes = 0
        for ligne in request.POST.get("liste", "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            parts = [p.strip() for p in ligne.replace("\t", ";").split(";")]
            prenom = parts[0]
            nom = parts[1] if len(parts) > 1 else ""
            niveau = (
                parts[2].upper()
                if len(parts) > 2 and parts[2].upper() in {"PS", "MS", "GS"}
                else niveau_defaut
            )
            Eleve.objects.create(
                classe=classe, prenom=prenom, nom=nom, niveau=niveau
            )
            ajoutes += 1
        messages.success(request, f"{ajoutes} enfant(s) ajouté(s) à {classe}.")
        return redirect("classe_detail", pk=classe.pk)

    return render(request, "suivi/importer_eleves.html", {"classe": classe})
