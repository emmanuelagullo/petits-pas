from django import forms
from django.utils import timezone
from .models import NIVEAUX


class SelectionElevesForm(forms.Form):
    eleves = forms.TypedMultipleChoiceField(label="Élèves concernés", coerce=int,
        widget=forms.CheckboxSelectMultiple,
        help_text="Seuls ces élèves seront concernés. L’activation du suivi n’attribue aucune réussite.")
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
    sous_domaine = forms.TypedChoiceField(label="Sous-domaine", coerce=int, required=False, empty_value=None,
        help_text="Facultatif. Choisissez un sous-domaine du domaine indiqué ; les autres seront refusés.")
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
        noms = dict(self.fields["domaine"].choices)
        self.fields["sous_domaine"].choices = [("", "Sans sous-domaine")] + [
            (s["id"], f"{noms[s['domaine_id']]} — {s['nom']}") for s in contenu.get("sous_domaines", [])]
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
