"""Choix annuels de l'école ; le service valide les règles communes."""
from django import forms


class ChoixEcoleForm(forms.Form):
    autorisations = forms.ChoiceField(label="Bases que les classes pourront choisir", choices=[
        ("garder", "Garder toutes les bases autorisées par l'application"),
        ("restreindre", "Conserver une liste plus courte pour l'école"),
    ], widget=forms.RadioSelect)
    versions = forms.TypedMultipleChoiceField(label="Liste choisie par l'école", required=False,
        coerce=int, widget=forms.CheckboxSelectMultiple,
        help_text="Cette liste sert uniquement si vous choisissez de conserver une liste plus courte.")
    proposee = forms.TypedChoiceField(label="Base proposée par défaut", coerce=int,
        empty_value=None, required=False)

    def __init__(self, *args, versions, **kwargs):
        super().__init__(*args, **kwargs)
        choix = [(v.pk, f"{v.source.titre} — version {v.numero}") for v in versions]
        self.fields["versions"].choices = choix
        self.fields["proposee"].choices = [("", "Garder le choix proposé par l'application")] + choix

    def clean(self):
        donnees = super().clean()
        donnees["restreindre"] = donnees.get("autorisations") == "restreindre"
        if not donnees["restreindre"]:
            donnees["versions"] = []
        return donnees


class AdaptationCompetenceForm(forms.Form):
    mode_libelle = forms.ChoiceField(label="Libellé", choices=[
        ("garder", "Garder le libellé proposé"), ("personnel", "Utiliser mon libellé")], widget=forms.RadioSelect)
    libelle = forms.CharField(label="Mon libellé", max_length=300, required=False,
                             widget=forms.Textarea(attrs={"rows": 2}))
    meme_sens = forms.BooleanField(label="Mon libellé décrit le même apprentissage.", required=False)
    visibilite = forms.ChoiceField(label="Dans les prochaines saisies", choices=[
        ("garder", "Garder la visibilité proposée"), ("montrer", "Montrer cette compétence"),
        ("masquer", "Masquer cette compétence")], widget=forms.RadioSelect)

    def clean(self):
        donnees = super().clean()
        if donnees.get("mode_libelle") == "personnel":
            if not donnees.get("libelle"):
                self.add_error("libelle", "Précisez votre libellé.")
            if not donnees.get("meme_sens"):
                self.add_error("meme_sens", "Confirmez que le même apprentissage est conservé.")
        else:
            donnees["libelle"] = None
        donnees["visible"] = {"garder": None, "montrer": True, "masquer": False}.get(donnees.get("visibilite"))
        return donnees


class AjoutCompetenceForm(forms.Form):
    libelle = forms.CharField(label="Apprentissage", max_length=300,
                             widget=forms.Textarea(attrs={"rows": 2}))
    niveau = forms.ChoiceField(label="Section", choices=[("PS", "Petite section"),
                              ("MS", "Moyenne section"), ("GS", "Grande section")])
    domaine = forms.TypedChoiceField(label="Domaine", coerce=int)

    def __init__(self, *args, domaines, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["domaine"].choices = [(d["id"], d["nom"]) for d in domaines]
