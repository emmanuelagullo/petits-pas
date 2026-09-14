from django.contrib import admin

from .models import Classe, Competence, Domaine, Ecole, Eleve, Observation


class EleveInline(admin.TabularInline):
    model = Eleve
    extra = 0


@admin.register(Ecole)
class EcoleAdmin(admin.ModelAdmin):
    list_display = ("nom", "commune", "cree_le")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("nom", "ecole", "annee_scolaire", "ordre")
    inlines = [EleveInline]


@admin.register(Eleve)
class EleveAdmin(admin.ModelAdmin):
    list_display = ("prenom", "nom", "niveau", "classe")
    list_filter = ("classe", "niveau")
    search_fields = ("prenom", "nom")


class CompetenceInline(admin.TabularInline):
    model = Competence
    extra = 0


@admin.register(Domaine)
class DomaineAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "ecole", "ordre")
    inlines = [CompetenceInline]


@admin.register(Competence)
class CompetenceAdmin(admin.ModelAdmin):
    list_display = ("libelle", "code", "niveau", "domaine", "active")
    list_filter = ("domaine", "niveau", "active")
    search_fields = ("libelle", "code")


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("eleve", "competence", "statut", "date_observation")
    list_filter = ("statut", "eleve__classe")
