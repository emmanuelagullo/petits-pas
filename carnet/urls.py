from django.urls import include, path
from .maintenance import annonce

urlpatterns = [
    path("maintenance-annonce/", annonce, name="maintenance_annonce"),
    path("", include("suivi.urls")),
]
