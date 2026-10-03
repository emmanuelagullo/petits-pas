"""Les droits métier restent ceux des vues communes ; seul le rendu change."""
from django.urls import include, path
from . import views

urlpatterns = [
    path("classe/<int:pk>/edition/", views.edition_imprimable),
    path("pwa/autoriser-recuperation/", views.autoriser_recuperation),
    path("eleve/<int:pk>/carnet.pdf", views.carnet_imprimable),
    path("classe/<int:pk>/competence/<int:competence_pk>/grille.pdf", views.grille_imprimable),
    path("", include("suivi.urls")),
]
