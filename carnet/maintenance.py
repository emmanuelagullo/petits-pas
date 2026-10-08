"""Annonce facultative de maintenance, sans accès à la base."""
import json
import math
import time
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def annonce(request):
    resultat = {"debut": None}
    chemin = getattr(settings, "MAINTENANCE_ANNONCE", "")
    if chemin:
        try:
            fichier = Path(chemin)
            if not fichier.is_symlink() and fichier.stat().st_size <= 1024:
                valeur = json.loads(fichier.read_text())
                debut, expiration = valeur["debut"], valeur["expiration"]
                if (type(debut) in (int, float) and type(expiration) in (int, float)
                    and math.isfinite(debut) and math.isfinite(expiration)
                    and debut <= expiration <= debut + 3600 and time.time() < expiration):
                    resultat["debut"] = debut
        except (OSError, ValueError, KeyError, TypeError):
            pass
    reponse = JsonResponse(resultat)
    reponse["Cache-Control"] = "no-store"
    return reponse
