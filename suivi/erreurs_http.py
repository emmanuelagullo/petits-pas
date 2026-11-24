"""Réponses de reprise indépendantes de la session."""
from django.shortcuts import render
from django.urls import reverse


def refus_csrf(request, reason=""):
    reponse = render(request, "suivi/refus_csrf.html", {"accueil_reprise": reverse("accueil")}, status=403)
    reponse["X-Petits-Pas-Refus"] = "csrf"
    reponse["Cache-Control"] = "no-store"
    return reponse
