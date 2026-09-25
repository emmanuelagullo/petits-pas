from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Utilisateur


class InstallationLocaleForm(UserCreationForm):
    """Première école et première identité, uniquement dans un paquet vide."""

    ecole_nom = forms.CharField(label="Nom de l’école", max_length=200)
    commune = forms.CharField(label="Commune", max_length=200, required=False)

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name")
        labels = {
            "username": "Nom d’utilisateur",
            "first_name": "Prénom",
            "last_name": "Nom",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            [
                "ecole_nom", "commune", "first_name", "last_name",
                "username", "password1", "password2",
            ]
        )
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmer le mot de passe"

    def clean_ecole_nom(self):
        nom = self.cleaned_data["ecole_nom"].strip()
        if not nom:
            raise ValidationError("Indiquez le nom de l’école.")
        return nom


class CreationCompteInvitationForm(UserCreationForm):
    """Crée une identité individuelle depuis une invitation vérifiée."""

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name")
        labels = {
            "username": "Nom d'utilisateur",
            "first_name": "Prénom",
            "last_name": "Nom",
        }

    def __init__(self, *args, email, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.email = email.strip().casefold()
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmation du mot de passe"

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        utilisateur.email = self.instance.email
        if commit:
            utilisateur.save()
        return utilisateur


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ("first_name", "last_name")
        labels = {"first_name": "Prénom", "last_name": "Nom"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
