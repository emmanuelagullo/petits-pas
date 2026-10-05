"""Formulaires communs aux parcours de préparation des classes."""
from django import forms
from django.utils import timezone
from suivi.models import annee_scolaire_pour
from suivi.services.choix_bases_referentiels import verifier_annee


class ClasseForm(forms.Form):
    nom = forms.CharField(label="Nom de la classe", max_length=100,
                          help_text="Par exemple : PS-MS de Nadia, Les Coccinelles.")
    annee_scolaire = forms.CharField(label="Année scolaire", max_length=9,
                                   validators=[verifier_annee],
                                   help_text="Deux années consécutives, par exemple 2026-2027.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annee_scolaire"].initial = annee_scolaire_pour(timezone.localdate())


class DroitsGestionForm(forms.Form):
    date_fin = forms.DateField(required=False, label="Fin éventuelle",
        widget=forms.DateInput(attrs={"type": "date"}))
    motif = forms.CharField(required=False, max_length=500, label="Motif")
