from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    pass


admin.site.register(AppartenanceEcole)
admin.site.register(ResponsabiliteEcole)
admin.site.register(AffectationClasse)
