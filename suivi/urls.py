from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.accueil, name="accueil"),
    path("connexion/", views.connexion, name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path(
        "invitation/<uuid:selecteur>/<str:jeton>/",
        views.accepter_invitation_vue,
        name="accepter_invitation",
    ),
    path("classe/<int:pk>/", views.classe_detail, name="classe_detail"),
    path(
        "classe/<int:pk>/collaborateurs/",
        views.collaborateurs_classe,
        name="collaborateurs_classe",
    ),
    path(
        "classe/<int:pk>/edition/",
        views.preparer_edition,
        name="preparer_edition",
    ),
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
    path(
        "classe/<int:pk>/competence/<int:competence_pk>/grille/",
        views.grille_competence,
        name="grille_competence",
    ),
    path(
        "classe/<int:pk>/competence/<int:competence_pk>/grille.pdf",
        views.grille_competence_pdf,
        name="grille_competence_pdf",
    ),
    path("eleve/<int:pk>/", views.saisie_eleve, name="saisie_eleve"),
    path(
        "eleve/<int:pk>/contribution/",
        views.contribuer_eleve,
        name="contribuer_eleve",
    ),
    path("eleve/<int:pk>/carnet/", views.carnet, name="carnet"),
    path("eleve/<int:pk>/bilans/", views.bilans_eleve, name="bilans_eleve"),
    path(
        "eleve/<int:pk>/bilans/<int:bilan_pk>/",
        views.modifier_bilan,
        name="modifier_bilan",
    ),
    path(
        "eleve/<int:pk>/bilans/<int:bilan_pk>/supprimer/",
        views.supprimer_bilan,
        name="supprimer_bilan",
    ),
    path(
        "eleve/<int:pk>/bilans/<int:bilan_pk>/visibilite/",
        views.basculer_visibilite_bilan,
        name="basculer_visibilite_bilan",
    ),
    path(
        "eleve/<int:pk>/carnet.pdf",
        views.carnet_pdf,
        name="carnet_pdf",
    ),
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
    path(
        "media/trace/<int:trace_pk>/",
        views.afficher_media_trace,
        name="afficher_media_trace",
    ),
    path(
        "media/trace/<int:trace_pk>/original/",
        views.telecharger_media_trace,
        name="telecharger_media_trace",
    ),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/trace/<int:trace_pk>/",
        views.modifier_trace,
        name="modifier_trace",
    ),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/trace/<int:trace_pk>/supprimer/",
        views.supprimer_trace,
        name="supprimer_trace",
    ),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/trace/<int:trace_pk>/restaurer/",
        views.restaurer_trace_vue,
        name="restaurer_trace",
    ),
    path(
        "eleve/<int:eleve_pk>/competence/<int:competence_pk>/trace/<int:trace_pk>/visibilite/",
        views.basculer_visibilite_trace,
        name="basculer_visibilite_trace",
    ),
    path("gestion/", views.gestion, name="gestion"),
    path("gestion/equipe/", views.equipe_ecole, name="equipe_ecole"),
    path("gestion/eleves/", views.annuaire_eleves, name="annuaire_eleves"),
    path(
        "gestion/parametres-carnet/",
        views.parametres_carnet,
        name="parametres_carnet",
    ),
    path("gestion/classe/nouvelle/", views.creer_classe, name="creer_classe"),
    path(
        "gestion/classe/<int:pk>/activer/",
        views.activer_classe_vue,
        name="activer_classe",
    ),
    path(
        "gestion/eleve/<int:pk>/parcours/",
        views.parcours_eleve,
        name="parcours_eleve",
    ),
    path(
        "gestion/classe/<int:pk>/eleves/",
        views.importer_eleves,
        name="importer_eleves",
    ),
    path("gestion/eleve/<int:pk>/archiver/", views.archiver_eleve, name="archiver_eleve"),
    path("gestion/eleve/<int:pk>/desarchiver/", views.desarchiver_eleve, name="desarchiver_eleve"),
]
