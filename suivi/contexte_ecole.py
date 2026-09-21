"""Choix du contexte d'école, distinct de la décision d'autorisation."""

from .autorisations import ACCEDER_APPLICATION, ecoles_accessibles


def ecole_courante(request):
    ecoles = ecoles_accessibles(request.user, ACCEDER_APPLICATION)
    ecole = ecoles.filter(pk=request.session.get("ecole_id")).first()
    if ecole is None:
        ecole = ecoles.first()
        if ecole:
            request.session["ecole_id"] = ecole.pk
        else:
            request.session.pop("ecole_id", None)
    return ecole
