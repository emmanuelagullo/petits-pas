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
        self.fields["proposee"].label = "Façon de commencer proposée aux classes"
        libres = [(v.pk, v.source.titre) for v in versions if v.contenu.get("structure_seule")]
        bases = [(v.pk, f"{v.source.titre} — version {v.numero}") for v in versions if not v.contenu.get("structure_seule")]
        self.fields["proposee"].choices = [("", "Garder le choix proposé par l'application")]
        if libres:
            self.fields["proposee"].choices.append(("Démarrer sans compétences prédéfinies", libres))
        if bases:
            self.fields["proposee"].choices.append(("Partir d’un référentiel", bases))

    def clean(self):
        donnees = super().clean()
        donnees["restreindre"] = donnees.get("autorisations") == "restreindre"
        if not donnees["restreindre"]:
            donnees["versions"] = []
        return donnees


class AdaptationCompetenceForm(forms.Form):
    mode_libelle = forms.ChoiceField(label="Libellé", choices=[
        ("garder", "Garder le libellé proposé"), ("personnel", "Utiliser mon libellé")], widget=forms.RadioSelect)
    libelle = forms.CharField(label="Mon libellé", max_length=300, required=False,
                             widget=forms.Textarea(attrs={"rows": 2}))
    visibilite = forms.ChoiceField(label="Dans les prochaines saisies", choices=[
        ("garder", "Garder la visibilité proposée"), ("montrer", "Montrer cette compétence"),
        ("masquer", "Masquer cette compétence")], widget=forms.RadioSelect)

    def __init__(self, *args, choix_garder="Garder le libellé proposé", libelle_direct=False,
                 visibilite_directe=False, choix_visibilite_garder="Garder la visibilité proposée", **kwargs):
        super().__init__(*args, **kwargs)
        self.libelle_direct = libelle_direct
        self.visibilite_directe = visibilite_directe
        self.fields["mode_libelle"].choices = [("garder", choix_garder), ("personnel", "Utiliser mon libellé")]
        if visibilite_directe:
            self.fields["visibilite"] = forms.BooleanField(
                label="Proposer cette compétence dans les prochaines saisies", required=False)
        else:
            self.fields["visibilite"].choices = [
                ("garder", choix_visibilite_garder), ("montrer", "Montrer cette compétence"),
                ("masquer", "Masquer cette compétence")]
        if libelle_direct:
            del self.fields["mode_libelle"]
            self.fields["libelle"].label = "Libellé de la compétence"
            self.fields["libelle"].required = True

    def clean(self):
        donnees = super().clean()
        if self.libelle_direct or donnees.get("mode_libelle") == "personnel":
            if not donnees.get("libelle"):
                self.add_error("libelle", "Précisez votre libellé.")
        else:
            donnees["libelle"] = None
        donnees["visible"] = (bool(donnees.get("visibilite")) if self.visibilite_directe else
            {"garder": None, "montrer": True, "masquer": False}.get(donnees.get("visibilite")))
        return donnees


class ClassementCompetenceForm(forms.Form):
    niveau = forms.ChoiceField(label="Section", choices=[("PS", "Petite section"),
                              ("MS", "Moyenne section"), ("GS", "Grande section")])
    domaine = forms.TypedChoiceField(label="Domaine", coerce=int)
    sous_domaine = forms.TypedChoiceField(label="Sous-domaine", coerce=int, required=False, empty_value=None)

    def __init__(self, *args, domaines, sous_domaines=(), conserver_domaine=False, **kwargs):
        super().__init__(*args, **kwargs)
        domaines = list(domaines)
        self.sous_domaines = {s["id"]: s for s in sous_domaines}
        self.fields["domaine"].choices = [(d["id"], d["nom"]) for d in domaines]
        if conserver_domaine:
            self.fields["domaine"].required = False
            self.fields["domaine"].empty_value = None
            self.fields["domaine"].choices = [("", "Conserver le domaine et le sous-domaine actuels"),
                                              *self.fields["domaine"].choices]
        self.fields["sous_domaine"].choices = [("", "Sans sous-domaine")] + [
            (d["nom"], [(s["id"], s["nom"]) for s in self.sous_domaines.values() if s["domaine_id"] == d["id"]])
            for d in domaines
        ]

    def clean(self):
        donnees = super().clean()
        sous = self.sous_domaines.get(donnees.get("sous_domaine"))
        if sous and sous["domaine_id"] != donnees.get("domaine"):
            self.add_error("sous_domaine", "Ce sous-domaine appartient à un autre domaine.")
        return donnees


class DeplacementCompetenceForm(ClassementCompetenceForm):
    niveau = None
    domaine = forms.TypedChoiceField(label="Rubrique de destination", coerce=int)
    sous_domaine = forms.TypedChoiceField(label="Sous-rubrique de destination", coerce=int, required=False,
                                          empty_value=None)

    def __init__(self, *args, sous_domaines=(), **kwargs):
        from .forms_suivi_libre import SousDomainesSelect

        super().__init__(*args, sous_domaines=sous_domaines, **kwargs)
        champ = self.fields["sous_domaine"]
        champ.choices = [("", "Sans sous-rubrique"), *list(champ.choices)[1:]]
        champ.widget = SousDomainesSelect({str(s["id"]): s["domaine_id"] for s in sous_domaines}, choices=champ.choices)


class AjoutCompetenceForm(ClassementCompetenceForm):
    libelle = forms.CharField(label="Description de la compétence", max_length=300,
                             widget=forms.Textarea(attrs={"rows": 2}))
    field_order = ["libelle", "niveau", "domaine", "sous_domaine"]


class CorrespondanceCompetenceForm(forms.Form):
    depart = forms.ChoiceField(label="La compétence que je veux situer")
    type_lien = forms.ChoiceField(label="Comment se situe-t-elle par rapport à l’autre ?", choices=[
        ("lien", "Les deux compétences se rapprochent"), ("precise", "Elle décrit une partie plus ciblée de l’autre"),
        ("remplace", "Je prévois de l’utiliser à la place de l’autre")])
    arrivee = forms.ChoiceField(label="L’autre compétence")
    justification = forms.CharField(label="Pourquoi relier ces compétences ?", max_length=1000,
                                   widget=forms.Textarea(attrs={"rows": 3}))
    consequences = forms.BooleanField(label="Ce lien ne copie aucune réussite et ne change pas les compétences proposées à la saisie.")

    def __init__(self, *args, catalogue, **kwargs):
        super().__init__(*args, **kwargs)
        choix = [("", "Choisir une compétence")] + [(r, f"{c['libelle']} · {c['niveau']} · {c['origine']}")
                    for r, c in catalogue.items()]
        self.fields["depart"].choices = choix
        self.fields["arrivee"].choices = choix


class PartageReferentielClasseForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .services.licences_diffusion import LICENCES_RECONNUES

        self.fields["licence_creations"].choices += [(licence, licence) for licence in sorted(LICENCES_RECONNUES)]
        for champ in self.fields.values():
            champ.widget.attrs["form"] = "informations-partage-classe"

    titre = forms.CharField(label="Titre du référentiel", max_length=200)
    identifiant = forms.RegexField(
        label="Identifiant du référentiel", regex=r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z", max_length=120,
        help_text="Gardez le même identifiant pour les prochaines éditions.",
    )
    version = forms.RegexField(label="Numéro d’édition", regex=r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z",
                               max_length=80, initial="1")
    provenance = forms.CharField(label="Provenance et crédits", max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))
    licence = forms.CharField(label="Licence", max_length=120, required=False)
    licence_creations = forms.ChoiceField(label="Licence proposée pour les créations sans licence", required=False,
                                         choices=(("", "Réglage de la classe (CC BY-SA 4.0 par défaut)"),))
