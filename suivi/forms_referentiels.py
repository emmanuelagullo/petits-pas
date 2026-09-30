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
