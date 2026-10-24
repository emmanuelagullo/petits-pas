from django import forms
from django.utils import timezone
from .models import NIVEAUX


class SousDomainesSelect(forms.Select):
    def __init__(self, domaines, **kwargs):
        self.domaines = domaines
        super().__init__(**kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        domaine = self.domaines.get(str(value))
        if domaine is not None:
            option["attrs"]["data-domaine"] = str(domaine)
        return option


class SelectionElevesForm(forms.Form):
    eleves = forms.TypedMultipleChoiceField(label="Élèves concernés", coerce=int,
        widget=forms.CheckboxSelectMultiple)
    jeton = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, classe, **kwargs):
        super().__init__(*args, **kwargs)
        self.classe = classe
        self.fields["eleves"].choices = [(e.pk, e.nom_court) for e in classe.eleves]


class ReussiteLibreForm(SelectionElevesForm):
    libelle = forms.CharField(label="Description de la compétence", max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Décrivez ce que les élèves savent faire. Cette compétence restera disponible pour compléter leur suivi.")
    domaine = forms.TypedChoiceField(label="Domaine", coerce=int)
    sous_domaine = forms.TypedChoiceField(label="Sous-domaine — facultatif", coerce=int, required=False, empty_value=None,
        help_text="Sans sous-domaine, la compétence est classée directement dans le domaine.")
    icone = forms.ChoiceField(label="Icône", required=False)
    niveau = forms.ChoiceField(label="Repère de section", choices=NIVEAUX, initial="PS")
    reussite = forms.BooleanField(label="Enregistrer une réussite", required=False)
    date_observation = forms.DateField(label="Date du constat", required=False, initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    commentaire = forms.CharField(label="Commentaire", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    photo = forms.ImageField(label="Photo de la réalisation", required=False)

    def __init__(self, *args, contenu, **kwargs):
        super().__init__(*args, **kwargs)
        self.contenu = contenu
        from .presentation import catalogue_icones
        self.fields["icone"].choices = [("", "Sans illustration")] + [(k, v["nom"]) for k, v in catalogue_icones().items()]
        self.fields["domaine"].choices = [(d["id"], d["nom"]) for d in contenu.get("domaines", [])]
        sous_domaines = contenu.get("sous_domaines", [])
        self.fields["sous_domaine"].widget = SousDomainesSelect(
            {str(s["id"]): s["domaine_id"] for s in sous_domaines})
        self.fields["sous_domaine"].choices = [("", "Sans sous-domaine")] + [
            (d["nom"], [(s["id"], s["nom"]) for s in sous_domaines if s["domaine_id"] == d["id"]])
            for d in contenu.get("domaines", [])
            if any(s["domaine_id"] == d["id"] for s in sous_domaines)]
        self.order_fields(["libelle", "domaine", "sous_domaine", "eleves", "niveau", "reussite", "date_observation", "commentaire", "photo", "jeton"])

    def clean(self):
        d = super().clean()
        if d.get("sous_domaine") and not any(s["id"] == d["sous_domaine"] and s["domaine_id"] == d.get("domaine")
                                           for s in self.contenu.get("sous_domaines", [])):
            self.add_error("sous_domaine", "Ce sous-domaine appartient à un autre domaine.")
        if (d.get("reussite") or d.get("commentaire") or d.get("photo")) and not d.get("date_observation"):
            self.add_error("date_observation", "Indiquez la date du constat.")
        from .models import bornes_annee_scolaire
        debut, fin = bornes_annee_scolaire(self.classe.annee_scolaire)
        if d.get("date_observation") and not debut <= d["date_observation"] <= fin:
            self.add_error("date_observation", "La date doit appartenir à l’année scolaire de la classe.")
        return d
