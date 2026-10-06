from django import forms
from .models import ReglagePresentation
from .presentation import catalogue_icones


class ImagePriveeInput(forms.ClearableFileInput):
    template_name = "suivi/widgets/image_privee.html"


class IllustrationForm(forms.ModelForm):
    icone = forms.ChoiceField(label="Icône fournie", required=False)

    class Meta:
        model = ReglagePresentation
        fields = ["mode", "icone", "photo"]
        widgets = {"photo": ImagePriveeInput}
        labels = {"mode": "Quelle image utiliser ?", "photo": "Image importée"}
        help_texts = {"photo": "JPEG, PNG ou WebP, 25 Mio maximum. L’image sera allégée et restera privée."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icone"].choices = [("", "Aucune icône fournie")]
        self.fields["icone"].choices += [(cle, valeur["nom"]) for cle, valeur in catalogue_icones().items()]
        if self.instance.competence_id is None:
            self.fields.pop("icone")
        self.fields["mode"].widget.attrs["title"] = "Utiliser l'image proposée, choisir votre image ou ne pas afficher d'image."
        self.fields["photo"].widget.attrs.update({
            "accept": "image/jpeg,image/png,image/webp",
            "data-image-privee": "trace" if self.instance.competence_id else "couverture",
        })
        # Les contrôles sont pilotés en JavaScript ; côté serveur, ignorer
        # également les modifications d'image hors du mode Remplacer.
        if self.is_bound and self.data.get("mode") != ReglagePresentation.REMPLACER:
            for nom in ("icone", "photo"):
                if nom in self.fields:
                    self.fields[nom].disabled = True

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "content_type"):
            if getattr(photo.image, "format", "") not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Choisissez une image JPEG, PNG ou WebP.")
        return photo
