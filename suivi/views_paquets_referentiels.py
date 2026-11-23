"""Diffusion des éditions publiques accessibles dans le contexte courant."""
import hashlib

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE,
                            autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .identites_referentiels import competences_document, reference_competence
from .models import annee_scolaire_pour
from .presentation import catalogue_icones
from .services.choix_bases_referentiels import choix_bases
from .services.import_sources_referentiels import importer_source, lire_source
from .services.paquets_referentiels import MAX_ARCHIVE, exporter_paquet, exporter_selection, lire_paquet
from .views import acces_requis

SEL = "diffusion-referentiel"


@acces_requis
@require_http_methods(["GET", "POST"])
def paquets_referentiels(request, classe_pk=None):
    ecole = ecole_courante(request)
    classe = None
    if classe_pk is not None:
        classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    elif not autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        raise PermissionDenied
    annee = classe.annee_scolaire if classe else request.GET.get("annee") or annee_scolaire_pour(timezone.localdate())
    versions = {}
    contexte = {"classe": classe, "annee": annee, "peut_importer": request.user.is_superuser}
    try:
        versions = {str(v.pk): v for v in choix_bases(ecole, annee).versions if v.source.ecole_id is None}
        version = versions.get(request.GET.get("edition"))
        if version:
            contexte["edition"] = version
            contexte["competences"] = [
                (reference_competence(c), c["libelle"]) for c in competences_document(version.contenu)
            ]
        if request.method == "POST":
            action = request.POST.get("action")
            if action in ("edition", "selection"):
                if version is None:
                    raise PermissionDenied
                donnees = (exporter_paquet(version) if action == "edition" else
                           exporter_selection(version, request.POST.getlist("competence")))
                reponse = HttpResponse(donnees, content_type="application/zip")
                reponse["Content-Disposition"] = 'attachment; filename="referentiel.zip"'
                return reponse
            if not request.user.is_superuser:
                raise PermissionDenied
            fichier = request.FILES.get("paquet")
            if not fichier:
                raise ValidationError("Choisissez le fichier à examiner.")
            donnees = fichier.read(MAX_ARCHIVE + 1)
            if action not in ("importer", "apercu"):
                raise ValidationError("Action inconnue.")
            document = lire_paquet(donnees)
            engagement = {"empreinte": hashlib.sha256(donnees).hexdigest(), "auteur": request.user.pk,
                          "ecole": ecole.pk, "classe": classe_pk, "annee": annee}
            if action == "importer":
                try:
                    attendu = signing.loads(request.POST.get("jeton", ""), salt=SEL, max_age=1800)
                except signing.BadSignature as erreur:
                    raise ValidationError("Préparez de nouveau l’aperçu du fichier.") from erreur
                if attendu != engagement:
                    raise ValidationError("Le fichier ou le contexte diffère de l’aperçu.")
                _, cree, _ = importer_source(document)
                contexte["message"] = ("Édition ajoutée au catalogue de l’application." if cree else
                                       "Cette édition figure déjà dans le catalogue de l’application.")
            else:
                importer_source(document, verifier_seulement=True)
                contenu, _ = lire_source(document)
                contexte["apercu"] = contenu
                competences = list(competences_document(contenu))
                contexte["competences_importees"] = competences
                icones = catalogue_icones()
                contexte["icones_importees"] = [icones[cle] for cle in sorted({c["icone"] for c in competences if c["icone"]})]
                contexte["jeton"] = signing.dumps(engagement, salt=SEL)
    except ValidationError as erreur:
        contexte["erreur"] = " ".join(erreur.messages)
    except IntegrityError:
        contexte["erreur"] = "Le catalogue a changé pendant l’import. Consultez de nouveau l’aperçu."
    contexte["versions"] = versions.values()
    return render(request, "suivi/paquets_referentiels.html", contexte, status=400 if "erreur" in contexte else 200)
