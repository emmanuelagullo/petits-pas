from django.urls import path

from . import views

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("connexion/", views.connexion, name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("classe/<int:pk>/", views.classe_detail, name="classe_detail"),
    path(
        "classe/<int:pk>/competences/",
        views.choisir_competence,
        name="choisir_competence",
    ),
    path(
        "classe/<int:pk>/competence/<int:competence_pk>/",
        views.saisie_competence,
        name="saisie_competence",
    ),
    path("eleve/<int:pk>/", views.saisie_eleve, name="saisie_eleve"),
    path("eleve/<int:pk>/carnet/", views.carnet, name="carnet"),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/basculer/",
        views.basculer,
        name="basculer",
    ),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/trace/",
        views.trace,
        name="trace",
    ),
    path("gestion/", views.gestion, name="gestion"),
    path("gestion/classe/nouvelle/", views.creer_classe, name="creer_classe"),
    path(
        "gestion/classe/<int:pk>/eleves/",
        views.importer_eleves,
        name="importer_eleves",
    ),
]
