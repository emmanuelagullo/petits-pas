from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Petits Pas — transition #A1", {"fields": ("ecole", "profil_transition")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Petits Pas — transition #A1", {"fields": ("ecole", "profil_transition")}),
    )
    list_display = UserAdmin.list_display + ("ecole", "profil_transition")
    list_filter = UserAdmin.list_filter + ("ecole", "profil_transition")
