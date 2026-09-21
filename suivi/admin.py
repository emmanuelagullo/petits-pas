from django.contrib import admin

from .models import (
    Attendu,
    Bilan,
    Classe,
    Competence,
    Domaine,
    Ecole,
    Eleve,
    EvenementAudit,
    FormulationProposee,
    Observation,
    ParametresCarnet,
    Scolarite,
    SousDomaine,
    Trace,
)


@admin.register(EvenementAudit)
class EvenementAuditAdmin(admin.ModelAdmin):
    list_display = ("cree_le", "ecole", "acteur", "action", "modele", "objet_id")
    list_filter = ("ecole", "action", "modele")
    readonly_fields = (
        "ecole",
        "acteur",
        "action",
        "modele",
        "objet_id",
        "anciennes_valeurs",
        "nouvelles_valeurs",
        "cree_le",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ParametresCarnet)
class ParametresCarnetAdmin(admin.ModelAdmin):
    list_display = ("ecole", "contenu_par_defaut", "regroupement_par_defaut")


class ScolariteInline(admin.TabularInline):
    model = Scolarite
    extra = 0


@admin.register(Ecole)
class EcoleAdmin(admin.ModelAdmin):
    list_display = ("nom", "commune", "cree_le")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("nom", "ecole", "annee_scolaire", "ordre")
    inlines = [ScolariteInline]


@admin.register(Eleve)
class EleveAdmin(admin.ModelAdmin):
    list_display = ("prenom", "nom", "ecole", "annee_naissance", "archive_le")
    list_filter = ("ecole", "archive_le")
    search_fields = ("prenom", "nom")
    inlines = [ScolariteInline]


@admin.register(Scolarite)
class ScolariteAdmin(admin.ModelAdmin):
    list_display = ("eleve", "classe", "niveau", "annee_scolaire")
    list_filter = ("annee_scolaire", "niveau", "classe")


@admin.register(Bilan)
class BilanAdmin(admin.ModelAdmin):
    list_display = ("scolarite", "date_bilan", "modifie_le")
    list_filter = ("scolarite__annee_scolaire",)


class CompetenceInline(admin.TabularInline):
    model = Competence
    extra = 0


@admin.register(Domaine)
class DomaineAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "ecole", "ordre")
    inlines = [CompetenceInline]


@admin.register(SousDomaine)
class SousDomaineAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "domaine", "ordre")


@admin.register(Attendu)
class AttenduAdmin(admin.ModelAdmin):
    list_display = ("code", "domaine", "ordre", "texte")


@admin.register(Competence)
class CompetenceAdmin(admin.ModelAdmin):
    list_display = (
        "libelle",
        "code",
        "niveau",
        "domaine",
        "sous_domaine",
        "active",
    )
    list_filter = ("domaine", "niveau", "active")
    search_fields = ("libelle", "code")


@admin.register(FormulationProposee)
class FormulationProposeeAdmin(admin.ModelAdmin):
    list_display = ("code", "competence", "ordre", "active")
    list_filter = ("active", "competence__domaine")


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("eleve", "competence", "statut", "date_observation")
    list_filter = ("statut", "eleve__scolarites__classe")


@admin.register(Trace)
class TraceAdmin(admin.ModelAdmin):
    list_display = (
        "observation",
        "date_observation",
        "scolarite",
        "visible_carnet",
    )
    list_filter = ("visible_carnet", "scolarite__annee_scolaire")
