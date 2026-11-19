from collections import Counter, defaultdict

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .autorisations import GERER_REFERENTIEL_CLASSE, charger_classe_autorisee
from .contexte_ecole import ecole_courante
from .navigation import chemin_classe, lien
from .referentiels import adoption_courante, arbre_version, contenu_adoption
from .rubriques import rattachements_rubriques, rubriques_masquees
from .services.rubriques import deplacer_rubrique, enregistrer_rubrique
from .views import acces_requis


class RubriqueForm(forms.Form):
    adoption_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    genre = forms.ChoiceField(choices=[("domaine", "Rubrique"), ("sous_domaine", "Sous-rubrique")], widget=forms.HiddenInput)
    domaine_id = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    rubrique_id = forms.IntegerField(min_value=1, required=False, widget=forms.HiddenInput)
    nom = forms.CharField(label="Nom", max_length=200, required=False)
    operation = forms.ChoiceField(choices=[("nom", "Nom"), ("visibilite", "Visibilité")], required=False)
    ordre = forms.IntegerField(min_value=0, max_value=32767, required=False, widget=forms.HiddenInput)
    masquee = forms.BooleanField(label="Masquer pour la saisie", required=False)

    def clean(self):
        valeurs = super().clean()
        operation = valeurs.pop("operation", "")
        if operation == "visibilite" and valeurs.get("rubrique_id"):
            valeurs["nom"] = None
        elif not valeurs.get("nom"):
            self.add_error("nom", "Saisissez le nom de la rubrique.")
        if operation == "nom":
            valeurs["masquee"] = None
        return valeurs


class OrdreRubriqueForm(forms.Form):
    adoption_id = forms.IntegerField(min_value=1)
    genre = forms.ChoiceField(choices=RubriqueForm.base_fields["genre"].choices)
    domaine_id = forms.IntegerField(min_value=1, required=False)
    rubrique_id = forms.IntegerField(min_value=1)
    ordre_initial = forms.CharField(max_length=50000)
    action = forms.ChoiceField(choices=[(action, action) for action in ("monter", "descendre", "glisser")])
    cible_id = forms.IntegerField(min_value=1, required=False)
    apres = forms.BooleanField(required=False)

    def clean_ordre_initial(self):
        try:
            return [int(pk) for pk in self.cleaned_data["ordre_initial"].split(",")]
        except ValueError as cause:
            raise ValidationError("L’ordre reçu est invalide.") from cause


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
        reordonner = request.POST.get("action") in ("monter", "descendre", "glisser")
        formulaire = (OrdreRubriqueForm if reordonner else RubriqueForm)(request.POST)
        if ouvert and formulaire.is_valid():
            try:
                action = deplacer_rubrique if reordonner else enregistrer_rubrique
                action(request.user, classe, **formulaire.cleaned_data)
            except ValidationError as cause:
                erreur = " ".join(cause.messages)
            else:
                if reordonner:
                    messages.success(request, "Ordre mis à jour.")
                    return redirect(lien("gerer_rubriques", classe.pk, ordre=1,
                                         ancre=f'{formulaire.cleaned_data["genre"]}-{formulaire.cleaned_data["rubrique_id"]}'))
                messages.success(request, "Rubrique enregistrée.")
                return redirect("gerer_rubriques", pk=classe.pk)
        else:
            erreur = "Vérifiez la rubrique et les paramètres de la classe."
    groupes = defaultdict(list)
    arbre = arbre_version(classe.ecole, contenu, masquer=False) if ouvert else []
    parents, enfants = rattachements_rubriques(adoption, arbre, [
        s for d in arbre for s in d.sous_domaines_lus
    ])
    compte_domaine, compte_groupe = Counter(), Counter()
    for competence in contenu.get("competences", []):
        domaine_id, groupe_id = competence["domaine_id"], competence["sous_domaine_id"]
        domaines_vises = {domaine_id, parents.get(domaine_id, domaine_id)}
        groupes_vises = {groupe_id, enfants.get(groupe_id, groupe_id)}
        if competence["active"] and not (domaines_vises & domaines_masques or groupes_vises & sous_domaines_masques):
            compte_domaine.update(domaines_vises)
            compte_groupe.update(groupes_vises)
    for sous in contenu.get("sous_domaines", []):
        groupes[sous["domaine_id"]].append({**sous, "masquee": sous["id"] in sous_domaines_masques,
                                            "nombre": compte_groupe[sous["id"]]})
    domaines = [{**d, "nom_affiche": d["nom"].removeprefix("Ajouts — ") if d["code"].startswith("ajout-") else d["nom"],
                 "groupes": groupes[d["id"]], "masquee": d["id"] in domaines_masques,
                 "nombre": compte_domaine[d["id"]]} for d in contenu.get("domaines", [])]
    ordre_domaines = ",".join(str(d["id"]) for d in domaines)
    for domaine in domaines:
        domaine["ordre_groupes"] = ",".join(str(s["id"]) for s in domaine["groupes"])
    ariane = chemin_classe(classe) + [("Référentiel de la classe", lien("referentiel_classe", classe.pk))]
    return render(request, "suivi/gerer_rubriques.html", {
        "classe": classe, "adoption": adoption, "ouvert": ouvert, "domaines": domaines, "ariane": ariane,
        "erreur": erreur, "formulaire": formulaire, "ordre_domaines": ordre_domaines,
        "mode_ordre": ouvert and request.GET.get("ordre") == "1",
    }, status=400 if erreur else 200)
