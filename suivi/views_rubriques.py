from collections import Counter, defaultdict

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, charger_classe_autorisee
from .contexte_ecole import ecole_courante
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante, contenu_adoption
from .rubriques import rubriques_masquees
from .services.rubriques import enregistrer_rubrique
from .views import acces_requis


class RubriqueForm(forms.Form):
    adoption_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    genre = forms.ChoiceField(choices=[("domaine", "Rubrique"), ("sous_domaine", "Sous-rubrique")], widget=forms.HiddenInput)
    domaine_id = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    rubrique_id = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    nom = forms.CharField(label="Nom", max_length=200)
    ordre = forms.IntegerField(label="Position", min_value=0, max_value=32767, initial=0)
    masquee = forms.BooleanField(label="Masquer pour la saisie", required=False)


@acces_requis
@require_http_methods(["GET", "POST"])
def gerer_rubriques(request, pk):
    classe = charger_classe_autorisee(request.user, pk, GERER_REFERENTIEL_CLASSE, ecole=ecole_courante(request))
    adoption = adoption_courante(classe)
    ouvert = bool(adoption and not adoption.clos)
    contenu = contenu_adoption(adoption) if adoption else {}
    domaines_masques, sous_domaines_masques = rubriques_masquees(classe)
    erreur = ""
    formulaire = None
    if request.method == "POST":
        formulaire = RubriqueForm(request.POST)
        if ouvert and formulaire.is_valid():
            try:
                enregistrer_rubrique(request.user, classe, **formulaire.cleaned_data)
            except ValidationError as cause:
                erreur = " ".join(cause.messages)
            else:
                messages.success(request, "Rubrique enregistrée.")
                return redirect("gerer_rubriques", pk=classe.pk)
        else:
            erreur = "Vérifiez la rubrique et les paramètres de la classe."
    groupes = defaultdict(list)
    compte_domaine = Counter(c["domaine_id"] for c in contenu.get("competences", []))
    compte_groupe = Counter(c["sous_domaine_id"] for c in contenu.get("competences", []))
    for sous in contenu.get("sous_domaines", []):
        groupes[sous["domaine_id"]].append({**sous, "masquee": sous["id"] in sous_domaines_masques,
                                            "nombre": compte_groupe[sous["id"]]})
    domaines = [{**d, "groupes": groupes[d["id"]], "masquee": d["id"] in domaines_masques,
                 "nombre": compte_domaine[d["id"]]} for d in contenu.get("domaines", [])]
    ariane = chemin_classe(classe) + [("Référentiel de la classe", lien("referentiel_classe", classe.pk))]
    return render(request, "suivi/gerer_rubriques.html", {
        "classe": classe, "adoption": adoption, "ouvert": ouvert, "domaines": domaines, "ariane": ariane,
        "erreur": erreur, "formulaire": formulaire,
    }, status=400 if erreur else 200)
