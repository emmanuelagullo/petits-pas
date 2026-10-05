from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from carnet.double_facteur import (
    ASSOCIE, AUCUN, CONTRIBUTEUR, DIRECTION, JAMAIS, RESPONSABLE, SANS_FONCTION,
)

from .autorisations import ADMINISTRER_ECOLE, autorise
from .contexte_ecole import ecole_courante
from .double_facteur import apercu_ecole, politique_deployeur
from .services.double_facteur import enregistrer_politique_ecole, lire_politique_ecole
from .views import acces_requis

# Libellés de la liste « obligatoire pour… » : chaque rang inclut les précédents.
CHOIX_OBLIGATOIRE = [
    (AUCUN, "Personne en plus de ce que fixe l'hébergeur"),
    (DIRECTION, "La direction"),
    (RESPONSABLE, "La direction et les responsables de classe"),
    (ASSOCIE, "…et les enseignants associés"),
    (CONTRIBUTEUR, "…et les contributeurs"),
    (SANS_FONCTION, "Toutes les personnes de l'école"),
]
# Libellés de la liste « indisponible pour… » : chaque rang inclut les suivants.
CHOIX_DESACTIVE = [
    (JAMAIS, "Personne : le second facteur reste proposé à tous"),
    (SANS_FONCTION, "Les personnes sans fonction"),
    (CONTRIBUTEUR, "…et les contributeurs"),
    (ASSOCIE, "…et les enseignants associés"),
    (RESPONSABLE, "…et les responsables de classe"),
    (DIRECTION, "Tout le monde, direction comprise"),
]


def _entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


@never_cache
@acces_requis
def double_facteur_ecole(request):
    """Politique de 2FA de l'école, sous celle de l'hébergeur."""
    if not settings.DOUBLE_FACTEUR_DISPONIBLE:
        raise Http404
    ecole = ecole_courante(request)
    if not autorise(request.user, ADMINISTRER_ECOLE, ecole):
        raise PermissionDenied
    erreur = None
    if request.method == "POST":
        try:
            enregistrer_politique_ecole(
                utilisateur=request.user, ecole=ecole,
                obligatoire_jusqu_au_rang=_entier(request.POST.get("obligatoire")),
                desactive_a_partir_du_rang=_entier(request.POST.get("desactive")),
                revision_attendue=_entier(request.POST.get("revision")),
            )
        except ValidationError as exc:
            erreur = " ".join(exc.messages)
        else:
            messages.success(request, "La politique d'authentification à deux facteurs a été enregistrée.")
            return redirect("double_facteur_ecole")
    lecture = lire_politique_ecole(utilisateur=request.user, ecole=ecole)
    deployeur = politique_deployeur()
    choix_obligatoire = [
        {"rang": rang, "libelle": libelle,
         "indisponible": rang >= deployeur.desactive_a_partir_du_rang}
        for rang, libelle in CHOIX_OBLIGATOIRE
    ]
    choix_desactive = [
        {"rang": rang, "libelle": libelle,
         "indisponible": rang <= deployeur.obligatoire_jusqu_au_rang}
        for rang, libelle in CHOIX_DESACTIVE
    ]
    obligatoire = lecture["obligatoire_jusqu_au_rang"]
    desactive = lecture["desactive_a_partir_du_rang"]
    if erreur:
        # On garde ce que la personne venait de choisir.
        obligatoire = _entier(request.POST.get("obligatoire"))
        desactive = _entier(request.POST.get("desactive"))
    return render(request, "suivi/double_facteur_ecole.html", {
        "ecole": ecole, "erreur": erreur, "revision": lecture["revision"],
        "obligatoire": obligatoire, "desactive": desactive,
        "choix_obligatoire": choix_obligatoire, "choix_desactive": choix_desactive,
        "deployeur": deployeur, "effective": lecture["effective"],
        "apercu": apercu_ecole(ecole),
        "deployeur_oblige": deployeur.obligatoire_jusqu_au_rang > AUCUN,
        "deployeur_desactive": deployeur.desactive_a_partir_du_rang < JAMAIS,
    })
