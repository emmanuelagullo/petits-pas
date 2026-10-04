from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Utilisateur


class InitialisationEcoleForm(UserCreationForm):
    """École et première identité : champs communs aux deux initialisations."""

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


class InstallationLocaleForm(InitialisationEcoleForm):
    """Préparer aussi le référentiel annuel et, si souhaité, la première classe."""

    preparer_classe = forms.BooleanField(label="Préparer aussi ma première classe", initial=True, required=False)
    referentiel = forms.ChoiceField(label="Référentiel de départ", initial="trame")
    annee_scolaire = forms.CharField(label="Année scolaire", max_length=9)
    classe_nom = forms.CharField(label="Nom de la classe", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from suivi.forms import ClasseForm
        from suivi.services.installation_locale import REFERENTIELS_DEPART
        classe = ClasseForm()
        self.fields["referentiel"].choices = [(cle, titre) for cle, titre, _ in REFERENTIELS_DEPART]
        self.fields["annee_scolaire"] = classe.fields["annee_scolaire"]
        self.fields["classe_nom"] = classe.fields["nom"]
        self.fields["classe_nom"].required = False
        self.order_fields([
            "ecole_nom", "commune", "first_name", "last_name",
            "username", "password1", "password2",
            "annee_scolaire", "referentiel", "preparer_classe", "classe_nom",
        ])

    def clean(self):
        donnees = super().clean()
        if donnees.get("preparer_classe"):
            from suivi.forms import ClasseForm
            classe = ClasseForm({"nom": donnees.get("classe_nom", ""),
                                "annee_scolaire": donnees.get("annee_scolaire", "")})
            if not classe.is_valid():
                for champ, erreurs in classe.errors.items():
                    cible = "classe_nom" if champ == "nom" else champ
                    if cible not in self.errors:
                        self.add_error(cible, erreurs)
        return donnees


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
