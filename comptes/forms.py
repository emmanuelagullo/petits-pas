from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from . import secours_local
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
    referentiel = forms.ChoiceField(label="Catalogue de départ", initial="trame")
    selection_manuelle = forms.BooleanField(label="Partir d’un suivi vide", required=False,
        help_text="Dans la première classe, vous choisirez les compétences à suivre dans le catalogue.")
    annee_scolaire = forms.CharField(label="Année scolaire", max_length=9)
    classe_nom = forms.CharField(label="Nom de la classe", max_length=100, required=False)
    dernier_recours = forms.BooleanField(
        label="Autoriser un dernier recours", initial=True, required=False,
        help_text="Si vous perdez à la fois votre mot de passe et votre clé de secours, "
                  "vous pourrez choisir un nouveau mot de passe depuis cet appareil, "
                  "sans perdre vos données.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.ACCES_LOCAL_AUTONOME:
            del self.fields["dernier_recours"]
        from suivi.forms import ClasseForm
        from suivi.services.installation_locale import REFERENTIELS_DEPART
        classe = ClasseForm()
        self.fields["referentiel"].choices = [
            ("Démarrer sans compétences prédéfinies", [("libre", "Catégories du cycle 1, sans compétences")]),
            ("Partir d’un référentiel", [(cle, titre) for cle, titre, _ in REFERENTIELS_DEPART if cle != "libre"])]
        self.fields["annee_scolaire"] = classe.fields["annee_scolaire"]
        self.fields["classe_nom"] = classe.fields["nom"]
        self.fields["classe_nom"].required = False
        self.order_fields([
            "ecole_nom", "commune", "first_name", "last_name",
            "username", "password1", "password2",
            "annee_scolaire", "referentiel", "preparer_classe", "classe_nom", "selection_manuelle",
            "dernier_recours",
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


class _NouveauMotDePasseForm(forms.Form):
    """Deux saisies d'un nouveau mot de passe, validé pour le compte concerné."""

    new_password1 = forms.CharField(
        label="Nouveau mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    compte_cible = None

    def full_clean(self):
        super().full_clean()
        # Chaque erreur est rattachée à son champ, pour les lecteurs d'écran.
        for nom in self.errors:
            if nom in self.fields:
                self.fields[nom].widget.attrs.update({
                    "aria-invalid": "true", "aria-describedby": f"erreur-{nom}"})

    def clean(self):
        donnees = super().clean()
        un, deux = donnees.get("new_password1"), donnees.get("new_password2")
        if un and deux and un != deux:
            self.add_error("new_password2", "Les deux mots de passe ne sont pas identiques.")
        elif un and deux and self.compte_cible is not None:
            try:
                validate_password(un, self.compte_cible)
            except ValidationError as erreur:
                self.add_error("new_password1", erreur)
        return donnees


class ReinitialisationParCleForm(_NouveauMotDePasseForm):
    """Nouveau mot de passe d'un compte reconnu par sa clé de secours."""

    cle = forms.CharField(
        label="Clé de secours", max_length=40,
        widget=forms.TextInput(attrs={
            "autocomplete": "off", "autocapitalize": "characters", "spellcheck": "false"}))

    def clean_cle(self):
        self.compte_cible = secours_local.compte_par_cle(self.cleaned_data["cle"])
        if self.compte_cible is None:
            raise ValidationError(
                "Cette clé n’est pas reconnue. Elle comporte seize signes, lettres et "
                "chiffres, en quatre groupes. Une clé plus ancienne a pu être remplacée.")
        return self.cleaned_data["cle"]


class DernierRecoursForm(_NouveauMotDePasseForm):
    """Choix du compte, puis nouveau mot de passe : le dernier recours de l'appareil."""

    compte = forms.ModelChoiceField(
        queryset=Utilisateur.objects.none(), label="Compte", empty_label="Choisir un compte",
        error_messages={"required": "Choisissez le compte à retrouver.",
                        "invalid_choice": "Ce compte n’est pas proposé sur cet appareil."})

    def __init__(self, *args, comptes, **kwargs):
        super().__init__(*args, **kwargs)
        self.comptes = list(comptes)
        self.fields["compte"].queryset = Utilisateur.objects.filter(
            pk__in=[c.pk for c in self.comptes])
        self.fields["compte"].label_from_instance = (
            lambda c: c.get_full_name() or c.username)
        if len(self.comptes) == 1:
            self.fields["compte"].initial = self.comptes[0].pk

    def clean_compte(self):
        self.compte_cible = self.cleaned_data["compte"]
        return self.compte_cible
