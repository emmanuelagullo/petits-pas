"""Les droits métier restent ceux des vues communes ; seul le rendu change."""
from django.urls import include, path
from . import partage_grist, views

urlpatterns = [
    path("pwa/invitation-grist/", partage_grist.invitation_grist, name="invitation_grist"),
    path("classe/<int:pk>/referentiel/espace-grist/", partage_grist.espace_classe, name="espace_grist_classe"),
    path("pwa/partage-grist/", partage_grist.synchroniser, name="synchroniser_grist"),
    path("gestion/sauvegardes-locales/", views.sauvegardes_progressives),
    path("verifier-zip/", views.verifier_zip_progressif),
    path("pwa/autoriser-recuperation/", views.autoriser_recuperation),
    path("eleve/<int:pk>/carnet.pdf", views.carnet_imprimable),
    path("", include("suivi.urls")),
]
