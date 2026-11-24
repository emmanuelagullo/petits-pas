"""Synchronisation de projections pédagogiques depuis le navigateur."""
import hashlib
import json
from uuid import UUID

import yaml
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import int_to_base36
from django.views.decorators.http import require_http_methods

from suivi.autorisations import GERER_REFERENTIEL_CLASSE, autorise, charger_classe_autorisee
from suivi.contexte_ecole import ecole_courante
from suivi.identites_referentiels import identifiant_source_ecole
from suivi.models import Classe, PartageGristClasse, SourceReferentiel, VersionReferentiel
from suivi.referentiels import adoption_courante
from suivi.services.catalogues_externes import HOTE_GRIST, TAILLE_MAX, adresse_grist
from suivi.services.import_sources_referentiels import importer_source
from suivi.services.partage_referentiel_classe import licences_referentiel_partage, preparer_referentiel_classe
from suivi.views import acces_requis

TABLE = "PetitsPasClasses"


def texte_json(objet):
    return json.dumps(objet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def empreinte(texte):
    return hashlib.sha256(texte.encode()).hexdigest()


def projection(partage):
    classe = partage.classe
    identifiant = f"classe-grist-{partage.identifiant}"
    titre = f"Référentiel de {classe.nom}"
    document = preparer_referentiel_classe(classe, {
        "identifiant": identifiant, "titre": titre, "provenance": "Espace de partage Petits Pas",
        "licence": partage.licence,
    }, "courante")
    if licences_referentiel_partage(adoption_courante(classe), document) != [partage.licence]:
        raise ValidationError("Vérifiez la licence des compétences avant le prochain envoi.")
    # Les références d’origine restent celles émises par la projection d’export.
    return texte_json(document)


@acces_requis
@require_http_methods(["GET", "POST"])
def espace_classe(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    partage = PartageGristClasse.objects.filter(classe=classe).first()
    erreur = ""
    if request.method == "POST":
        if request.POST.get("action") == "suspendre":
            PartageGristClasse.objects.filter(classe=classe).update(actif=False)
            return redirect("espace_grist_classe", pk=pk)
        try:
            adoption = adoption_courante(classe)
            if classe.etat != Classe.ACTIVE or not adoption or adoption.clos:
                raise ValidationError("Choisissez le référentiel d’une classe active avant de la connecter.")
            prefixe, document = adresse_grist(request.POST.get("grist", ""))
            licence = adoption.version.source.licence.strip()
            if not licence or licence.casefold() in {"non renseignée", "non renseigné", "inconnue"}:
                raise ValidationError("La licence du référentiel doit être renseignée avant le partage.")
            if request.POST.get("confirmer") != "oui":
                raise ValidationError("Confirmez le partage de vos compétences communes dans cet espace.")
            url = f"https://{HOTE_GRIST}{prefixe}/{document}"
            with transaction.atomic():
                Classe.objects.select_for_update().get(pk=classe.pk)
                partage, cree = PartageGristClasse.objects.get_or_create(classe=classe,
                    defaults={"url": url, "licence": licence})
                if not cree and (partage.url != url or partage.licence != licence or not partage.actif):
                    partage.url, partage.nom_espace, partage.derniere_empreinte = url, "", ""
                    partage.licence, partage.actif = licence, True
                    partage.save(update_fields=["url", "nom_espace", "derniere_empreinte", "licence", "actif"])
            return redirect("espace_grist_classe", pk=pk)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    return render(request, "suivi/espace_grist_classe.html", {"classe": classe, "partage": partage,
        "grist": request.POST.get("grist") or (partage.url if partage else request.GET.get("grist", "")),
        "erreur": erreur, "mode_pwa": True}, status=400 if erreur else 200)


def partages_autorises(request):
    ecole = ecole_courante(request)
    for partage in PartageGristClasse.objects.filter(classe__ecole=ecole,
            classe__etat=Classe.ACTIVE, actif=True).select_related("classe", "classe__ecole").order_by("pk"):
        if autorise(request.user, GERER_REFERENTIEL_CLASSE, partage.classe):
            adoption = adoption_courante(partage.classe)
            if adoption and not adoption.clos:
                yield partage


@transaction.atomic
def recevoir_projection(partage, ligne, propres):
    if not isinstance(ligne["Identifiant"], str):
        raise ValueError
    identifiant = str(UUID(ligne["Identifiant"]))
    if identifiant in propres:
        return
    contenu = ligne["Contenu"]
    if not isinstance(contenu, str) or len(contenu.encode()) > TAILLE_MAX:
        raise ValidationError("Référentiel partagé illisible ou trop volumineux.")
    document = json.loads(contenu)
    if not isinstance(document, dict) or not isinstance(document.get("source"), dict):
        raise ValidationError("Référentiel partagé illisible.")
    source_externe = document["source"]
    reference = f"classe-grist-{identifiant}"
    ecole = partage.classe.ecole
    existante = SourceReferentiel.objects.select_for_update().filter(ecole=ecole,
        identifiant=identifiant_source_ecole(ecole, reference)).first()
    document["source"] = {
        "identifiant": reference, "titre": existante.titre if existante else source_externe.get("titre"),
        "provenance": "Espace de partage Petits Pas",
        "licence": source_externe.get("licence"), "provisoire": True,
    }
    cle = empreinte(contenu)
    precedente = existante.versions.order_by("-pk").first() if existante else None
    if precedente and precedente.numero[:64] == cle:
        return
    document["version"] = cle if precedente is None else f"{cle}-{int_to_base36(precedente.pk)}"
    importer_source(yaml.safe_dump(document, allow_unicode=True), ecole=ecole)


@acces_requis
@require_http_methods(["GET", "POST"])
def synchroniser(request):
    if request.method == "GET":
        ecole = ecole_courante(request)
        propres = [str(pk) for pk in PartageGristClasse.objects.filter(classe__ecole=ecole)
                   .values_list("identifiant", flat=True)]
        recues = {}
        for identifiant, numero in VersionReferentiel.objects.filter(
                source__ecole=ecole, source__identifiant_diffusion__startswith="classe-grist-"
        ).order_by("-pk").values_list("source__identifiant_diffusion", "numero"):
            recues.setdefault(identifiant.removeprefix("classe-grist-"), numero[:64])
        travaux = []
        for partage in partages_autorises(request):
            prefixe, document = adresse_grist(partage.url)
            erreur = ""
            try:
                contenu = projection(partage)
                if len(contenu.encode()) > TAILLE_MAX:
                    raise ValidationError("Le référentiel est trop volumineux pour cet espace.")
            except ValidationError as cause:
                contenu, erreur = None, " ".join(cause.messages)
            cle = empreinte(contenu) if contenu else ""
            travaux.append({"id": str(partage.identifiant),
                "api": f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}",
                "table": TABLE, "nom": partage.classe.nom,
                "contenu": contenu if cle != partage.derniere_empreinte else None,
                "empreinte": cle, "recues": recues, "erreur": erreur})
        return JsonResponse({"partages": travaux, "propres": propres})
    if len(request.body) > 4 * TAILLE_MAX:
        return JsonResponse({"erreur": "Réponse Grist trop volumineuse."}, status=400)
    try:
        reponse = json.loads(request.body)
        if not isinstance(reponse, dict) or not isinstance(reponse.get("lignes"), list):
            raise ValueError
    except (ValueError, UnicodeError):
        return JsonResponse({"erreur": "Réponse Grist illisible."}, status=400)
    partage = next((p for p in partages_autorises(request) if str(p.identifiant) == reponse.get("id")), None)
    if not partage:
        raise Http404
    prefixe, document = adresse_grist(partage.url)
    if reponse.get("api") != f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}":
        return JsonResponse({"erreur": "L’espace de partage a changé."}, status=409)
    propres = {str(pk) for pk in PartageGristClasse.objects.filter(classe__ecole=partage.classe.ecole)
               .values_list("identifiant", flat=True)}
    erreurs = 0
    for ligne in reponse["lignes"]:
        try:
            if not isinstance(ligne, dict):
                raise ValueError
            recevoir_projection(partage, ligne, propres)
        except (KeyError, ValueError, ValidationError, TypeError):
            erreurs += 1
    nom = reponse.get("nom")
    if isinstance(nom, str):
        partage.nom_espace = nom[:200]
    confirme = reponse.get("confirme")
    # Un envoi retardé ne peut pas acquitter des changements locaux ultérieurs.
    if isinstance(confirme, str):
        try:
            if confirme == empreinte(projection(partage)):
                partage.derniere_empreinte = confirme
        except ValidationError:
            pass
    if not PartageGristClasse.objects.filter(pk=partage.pk, actif=True, url=partage.url).update(
            nom_espace=partage.nom_espace, derniere_empreinte=partage.derniere_empreinte):
        return JsonResponse({"erreur": "L’espace de partage a changé."}, status=409)
    return JsonResponse({"erreurs": erreurs, "nom": partage.nom_espace})
