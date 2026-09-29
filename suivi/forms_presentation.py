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
        labels = {"mode": "Choix local", "photo": "Image importée"}
        help_texts = {"photo": "JPEG, PNG ou WebP, 5 Mo maximum. Les images importées restent privées."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icone"].choices = [("", "Aucune icône fournie")]
        self.fields["icone"].choices += [(cle, valeur["nom"]) for cle, valeur in catalogue_icones().items()]
        if self.instance.competence_id is None:
            self.fields.pop("icone")

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "content_type"):
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("L'image dépasse 5 Mo.")
            if getattr(photo.image, "format", "") not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Choisissez une image JPEG, PNG ou WebP.")
        return photo
