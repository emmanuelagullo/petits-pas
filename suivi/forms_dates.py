from django import forms
from django.utils import timezone
from .models import bornes_annee_scolaire


class DateReussiteForm(forms.Form):
    choix = forms.ChoiceField(label="Date de la réussite", widget=forms.RadioSelect, initial="aujourdhui")
    date = forms.DateField(label="Autre date", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, precedente, annee, **kwargs):
        super().__init__(*args, **kwargs)
        self.annee = annee
        self.fields["choix"].choices = [("aujourdhui", "Aujourd’hui")]
        if precedente:
            self.fields["choix"].choices.append(("precedente", f"Conserver la précédente réussite du {precedente:%d/%m/%Y}"))
        self.fields["choix"].choices.append(("autre", "Choisir une date"))

    def clean(self):
        d = super().clean()
        if d.get("choix") == "autre":
            debut, fin = bornes_annee_scolaire(self.annee)
            if not d.get("date"):
                self.add_error("date", "Choisissez la date du constat.")
            elif not debut <= d["date"] <= fin:
                self.add_error("date", "La date doit appartenir à l’année scolaire.")
        else:
            d["date"] = timezone.localdate()
        return d
