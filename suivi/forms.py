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


class CreationClasseForm(ClasseForm):
    annee_scolaire = forms.CharField(widget=forms.HiddenInput, validators=[verifier_annee])
    base = forms.ChoiceField(label="Référentiel de départ", initial="ecole")
    jeton_choix = forms.CharField(widget=forms.HiddenInput)
    mot_de_passe = forms.CharField(label="Votre mot de passe pour un choix indépendant",
        required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, ecole, **kwargs):
        from django.core.exceptions import ValidationError
        from suivi.services.choix_bases_referentiels import choix_bases
        super().__init__(*args, **kwargs)
        annee = self.data.get("annee_scolaire") if self.is_bound else self.initial.get(
            "annee_scolaire", self.fields["annee_scolaire"].initial)
        self.annee = annee
        self.choix = None
        try:
            self.choix = choix_bases(ecole, annee)
        except ValidationError:
            pass  # Le validateur du champ explique l'année invalide.
        proposee = self.choix.proposee if self.choix else None
        if proposee:
            options = [("ecole", f"Utiliser le référentiel proposé par l’école : {proposee.source.titre} — version {proposee.numero}")]
        else:
            options = [("plus_tard", "Choisir après la création — aucun référentiel proposé pour cette année")]
        if self.choix:
            options.extend((str(v.pk), f"Choix indépendant : {v.source.titre} — version {v.numero}")
                           for v in self.choix.versions)
        self.fields["base"].choices = options
        self.fields["base"].initial = "ecole" if proposee else "plus_tard"


class DroitsGestionForm(forms.Form):
    date_fin = forms.DateField(required=False, label="Fin éventuelle",
        widget=forms.DateInput(attrs={"type": "date"}))
    motif = forms.CharField(required=False, max_length=500, label="Motif")
