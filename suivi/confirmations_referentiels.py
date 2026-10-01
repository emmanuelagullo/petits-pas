"""Confirmation commune ; le mot de passe ne quitte pas la requête."""
from django import forms
from django.contrib.auth import authenticate, login
from django.core.exceptions import ValidationError


class ConfirmationReferentielForm(forms.Form):
    mot_de_passe = forms.CharField(label="Votre mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, renforcee=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not renforcee:
            del self.fields["mot_de_passe"]


def verifier_confirmation(request, renforcee=True):
    form = ConfirmationReferentielForm(request.POST, renforcee=renforcee)
    if not form.is_valid():
        raise ValidationError("Saisissez votre mot de passe pour confirmer cette opération.")
    if renforcee:
        # Même authentification et même limitation des tentatives que la connexion.
        utilisateur = authenticate(request, username=request.user.get_username(),
                                   password=form.cleaned_data["mot_de_passe"])
        if not utilisateur or utilisateur.pk != request.user.pk:
            raise ValidationError("Le mot de passe n'a pas permis de confirmer cette opération.")
        login(request, utilisateur)
