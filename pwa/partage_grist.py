"""Synchronisation de projections pédagogiques depuis le navigateur."""
import hashlib
import json
from base64 import b64encode
from functools import wraps
from urllib.parse import urlencode
from uuid import UUID

import yaml
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import int_to_base36
from django.views.decorators.http import require_http_methods

from suivi.autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, autorise, charger_classe_autorisee
from suivi.contexte_ecole import ecole_courante
from suivi.icones_partagees import PREFIXE, decoder_icone, empreinte_png, externaliser_png
from suivi.identites_referentiels import competences_document, identifiant_source_classe, identifiant_source_ecole
from suivi.models import Classe, PartageGristClasse, ReceptionReferentielGrist, SourceReferentiel, VersionReferentiel
from suivi.referentiels import adoption_courante
from suivi.services.catalogues_externes import HOTE_GRIST, TAILLE_MAX, adresse_grist, partage_grist_disponible, referentiels_grist
from suivi.services.identites_grist import classes_grist_locales
from suivi.services.import_sources_referentiels import importer_source
from suivi.services.partage_referentiel_classe import preparer_referentiel_classe, verifier_licence_synchronisation
from suivi.views import acces_requis

TABLE = "PetitsPasClasses"


def partage_disponible(vue):
    @wraps(vue)
    def appel(request, *args, **kwargs):
        if not partage_grist_disponible():
            raise Http404
        return vue(request, *args, **kwargs)
    return appel


def texte_json(objet):
    return json.dumps(objet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def empreinte(texte):
    return hashlib.sha256(texte.encode()).hexdigest()


def nom_espace_propose(classe):
    return f"École {classe.ecole.nom} · Partage entre classes"[:200]


def document_projection(classe, identifiant):
    identifiant = f"classe-grist-{identifiant}"
    titre = f"Référentiel de {classe.nom}"
    document = preparer_referentiel_classe(classe, {
        "identifiant": identifiant, "titre": titre, "provenance": "Espace de partage Petits Pas",
        "licence": "",
    }, "courante")
    document["source"]["licence"] = verifier_licence_synchronisation(adoption_courante(classe), document)
    return document


def projection(partage, icones=None):
    document = document_projection(partage.classe, partage.identifiant)
    if document["source"]["licence"] != partage.licence:
        raise ValidationError("La licence a changé. Confirmez à nouveau le partage de cette classe.")
    # Les références d’origine restent celles émises par la projection d’export.
    ressources = externaliser_png(document)
    if icones is not None:
        icones.update({cle: b64encode(png).decode("ascii") for cle, png in ressources.items()})
    return texte_json(document)


@acces_requis
@require_http_methods(["GET"])
def invitation_grist(request):
    suivre = request.GET.get("usage") == "suivre"
    if not suivre and not partage_grist_disponible():
        raise Http404
    try:
        adresse_grist(request.GET.get("grist", ""))
    except ValidationError as cause:
        return render(request, "suivi/invitation_grist.html", {"erreur": cause.messages[0]}, status=400)
    url = request.GET.get("grist", "").strip()
    ecole = ecole_courante(request)
    if suivre and autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole):
        return redirect(reverse("decouvrir_referentiels") + "?" + urlencode({
            "catalogue_invite": url,
        }) + "#ajouter-catalogue")
    classes = []
    for classe in Classe.objects.filter(ecole=ecole, etat=Classe.ACTIVE).order_by("nom", "pk"):
        if not autorise(request.user, GERER_REFERENTIEL_CLASSE, classe):
            continue
        if suivre:
            classes.append((classe, reverse("suivis_referentiels_classe", args=[classe.pk])
                            + "?" + urlencode({"catalogue_invite": url}) + "#ajouter-catalogue"))
            continue
        adoption = adoption_courante(classe)
        if adoption and not adoption.clos:
            classes.append((classe, reverse("espace_grist_classe", args=[classe.pk])
                            + "?" + urlencode({"grist": url})))
    if len(classes) == 1:
        return redirect(classes[0][1])
    return render(request, "suivi/invitation_grist.html", {"classes": classes, "invitation_suivi": suivre})


def licence_raccordement(classe, partage, adoption):
    if adoption and not adoption.clos and classe.etat == Classe.ACTIVE:
        try:
            projection = document_projection(classe, partage.identifiant if partage else "preparation")
            return projection["source"]["licence"], "", sum(1 for _ in competences_document(projection))
        except ValidationError as cause:
            return "", " ".join(cause.messages), 0
    return "", "", 0


def contexte_raccordement(classe, partage, **options):
    if "licence" not in options:
        options["licence"], options["erreur_licence"], options["nombre_competences"] = licence_raccordement(classe, partage, adoption_courante(classe))
    return {
        "partage": partage,
        "grist": partage.url if partage else "",
        "espace_attendu": partage.url if partage else "",
        "nom_propose": nom_espace_propose(classe),
        "partage_confirme": bool(partage and partage.derniere_empreinte),
        "mode_pwa": getattr(settings, "MODE_PWA", False),
        **options,
    }


@partage_disponible
@acces_requis
@require_http_methods(["GET", "POST"])
def espace_classe(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    partage = PartageGristClasse.objects.filter(classe=classe).first()
    erreur = ""
    champ_erreur = ""
    adoption = adoption_courante(classe)
    licence, erreur_licence, nombre_competences = licence_raccordement(classe, partage, adoption)
    integre = request.GET.get("depuis") == "catalogues"
    retour_catalogues = reverse("suivis_referentiels_classe", args=[pk]) + "?espace=1#espace-partage"
    retour = retour_catalogues if integre else reverse("espace_grist_classe", args=[pk])
    nom_saisi = request.POST.get("nom_espace", "").strip()
    invitation = request.GET.get("grist", "")
    changer_destination = False
    request_confirmee = request.POST.get("confirmer") == "oui"
    if request.method == "GET" and invitation:
        try:
            _, document = adresse_grist(invitation)
            invitation = invitation.strip()
            if partage and adresse_grist(partage.url)[1] == document:
                return redirect(retour)
            changer_destination = bool(partage and partage.actif)
        except ValidationError as cause:
            erreur = cause.messages[0]
            invitation = ""
    if request.method == "POST":
        if request.POST.get("action") == "preparer-retrait":
            if not partage:
                raise Http404
            prefixe, document = adresse_grist(partage.url)
            if (request.POST.get("identifiant_attendu") != str(partage.identifiant)
                    or request.POST.get("url_attendue") != partage.url) or not PartageGristClasse.objects.filter(
                pk=partage.pk,
                identifiant=partage.identifiant,
                url=partage.url,
            ).update(actif=False, derniere_empreinte=""):
                return JsonResponse({"erreur": "Le raccordement a changé. Rechargez la page."}, status=409)
            return JsonResponse({"api": f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}",
                                 "identifiant": str(partage.identifiant)})
        if request.POST.get("action") == "suspendre":
            PartageGristClasse.objects.filter(classe=classe).update(actif=False)
            return redirect(retour)
        try:
            if request.POST.get("action") == "ouvrir-catalogue":
                adresse_grist(request.POST.get("grist", ""))
                if integre:
                    return redirect(reverse("suivis_referentiels_classe", args=[pk]) + "?" + urlencode({
                        "catalogue_invite": request.POST["grist"].strip(),
                    }) + "#ajouter-catalogue")
                return redirect(reverse("decouvrir_referentiels") + "?" + urlencode({
                    "catalogue_invite": request.POST["grist"].strip(), "gestion": "classe",
                    "classe": pk, "annee": classe.annee_scolaire,
                }) + "#ajouter-catalogue")
            if classe.etat != Classe.ACTIVE or not adoption or adoption.clos:
                raise ValidationError("Choisissez le référentiel d’une classe active avant de la connecter.")
            champ_erreur = "grist"
            _, document = adresse_grist(request.POST.get("grist", ""))
            champ_erreur = ""
            changer_destination = bool(partage and partage.actif and adresse_grist(partage.url)[1] != document)
            url = request.POST.get("grist", "").strip()
            if len(url) > 300:
                champ_erreur = "grist"
                raise ValidationError("Le lien de l’espace est limité à 300 caractères.")
            if partage and partage.actif and adresse_grist(partage.url)[1] == document and partage.licence == licence:
                PartageGristClasse.objects.filter(pk=partage.pk, url=partage.url, actif=True).update(url=url)
                return redirect(retour)
            if changer_destination and request.POST.get("changement") != document:
                # Présenter la destination avant de demander la confirmation.
                request_confirmee = False
                raise ValidationError("Vérifiez la nouvelle destination puis confirmez le changement d’espace.")
            if erreur_licence:
                raise ValidationError(erreur_licence)
            if request.POST.get("confirmer") != "oui":
                champ_erreur = "confirmer"
                raise ValidationError("Cochez cette case pour confirmer le partage, ou parcourez le catalogue dans Petits Pas.")
            if len(nom_saisi) > 200:
                champ_erreur = "nom_espace"
                raise ValidationError("Le nom de l’espace est limité à 200 caractères.")
            nom_initial = nom_saisi or nom_espace_propose(classe)
            with transaction.atomic():
                Classe.objects.select_for_update().get(pk=classe.pk)
                actuel = PartageGristClasse.objects.filter(classe=classe, actif=True).first()
                if actuel and adresse_grist(actuel.url)[1] != document and (
                    request.POST.get("espace_attendu") != actuel.url or request.POST.get("changement") != document
                ):
                    raise ValidationError("L’espace actif a changé. Vérifiez les destinations avant de confirmer.")
                partage, cree = PartageGristClasse.objects.get_or_create(classe=classe,
                    defaults={"url": url, "licence": licence, "nom_espace": nom_initial})
                if not cree and (partage.url != url or partage.licence != licence or not partage.actif):
                    if adresse_grist(partage.url)[1] != document:
                        partage.nom_espace = nom_initial
                        partage.editions_catalogue = None
                    partage.url, partage.derniere_empreinte = url, ""
                    partage.licence, partage.actif = licence, True
                    partage.save(update_fields=["url", "nom_espace", "derniere_empreinte", "licence", "actif", "editions_catalogue"])
            messages.info(request, "Espace rejoint. La synchronisation démarre dans Catalogues et partage.")
            return redirect(retour_catalogues)
        except ValidationError as cause:
            erreur = " ".join(cause.messages)
    document_actif = adresse_grist(partage.url)[1] if partage and partage.actif else ""
    contexte = contexte_raccordement(
        classe, partage, document_actif=document_actif,
        document_a_confirmer=document if changer_destination else "",
        grist=request.POST.get("grist") or invitation or (partage.url if partage else ""),
        erreur=erreur, champ_erreur=champ_erreur, licence=licence, erreur_licence=erreur_licence,
        nombre_competences=nombre_competences,
        confirmer=request_confirmee, nom_saisi=nom_saisi, changer_espace=bool(invitation or erreur),
        changer_destination=changer_destination,
    )
    if integre:
        from suivi.views_catalogues_referentiels import suivis_classe

        return suivis_classe(request, pk, contexte_espace=contexte)
    return render(request, "suivi/espace_grist_classe.html", {"classe": classe, **contexte},
                  status=400 if erreur else 200)


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
    icones = ligne.get("icones", {})
    for competence in competences_document(document):
        valeur = competence.get("icone_png")
        if isinstance(valeur, str) and valeur.startswith(PREFIXE):
            cle_icone = valeur[len(PREFIXE):]
            png = icones[cle_icone]
            if empreinte_png(decoder_icone(png)) != cle_icone:
                raise ValidationError("Une icône reçue ne correspond pas à son empreinte.")
            competence["icone_png"] = png
    source_externe = document["source"]
    reference = f"classe-grist-{identifiant}"
    ecole = partage.classe.ecole
    privee = partage.classe
    sources = SourceReferentiel.objects.select_for_update().filter(ecole=ecole)
    existante = sources.filter(identifiant=identifiant_source_classe(privee, reference)).first()
    if not existante:
        privee = None
        existante = sources.filter(identifiant=identifiant_source_ecole(ecole, reference)).first()
    document["source"] = {
        "identifiant": reference, "titre": existante.titre if existante else source_externe.get("titre"),
        "provenance": "Espace de partage Petits Pas",
        "licence": source_externe.get("licence"), "provisoire": True,
    }
    cle = empreinte(contenu)
    precedente = existante.versions.order_by("-pk").first() if existante else None
    if not precedente or precedente.numero[:64] != cle:
        document["version"] = cle if precedente is None else f"{cle}-{int_to_base36(precedente.pk)}"
        precedente, _, _ = importer_source(yaml.safe_dump(document, allow_unicode=True), ecole=ecole, classe=privee)
    ReceptionReferentielGrist.objects.get_or_create(source=precedente.source,
                                                  document_grist=adresse_grist(partage.url)[1])


@partage_disponible
@acces_requis
@require_http_methods(["GET", "POST"])
def synchroniser(request):
    if request.method == "GET":
        ecole = ecole_courante(request)
        propres = [reference.removeprefix("classe-grist-") for reference in classes_grist_locales(ecole)]
        travaux = []
        for partage in partages_autorises(request):
            prefixe, document = adresse_grist(partage.url)
            recues = {}
            for identifiant, numero in VersionReferentiel.objects.filter(
                    Q(source__classe_privee__isnull=True) | Q(source__classe_privee=partage.classe),
                    source__ecole=ecole, source__identifiant_diffusion__startswith="classe-grist-",
                    source__receptions_grist__document_grist=document,
            ).order_by("-pk").values_list("source__identifiant_diffusion", "numero"):
                recues.setdefault(identifiant.removeprefix("classe-grist-"), numero[:64])
            erreur = ""
            icones = {}
            try:
                contenu = projection(partage, icones)
                if len(contenu.encode()) + sum(map(len, icones.values())) > TAILLE_MAX:
                    raise ValidationError("Le référentiel est trop volumineux pour cet espace.")
            except ValidationError as cause:
                contenu, erreur = None, " ".join(cause.messages)
            cle = empreinte(contenu) if contenu else ""
            travaux.append({"id": str(partage.identifiant),
                "api": f"https://{HOTE_GRIST}{prefixe}/api/docs/{document}",
                "table": TABLE, "nom": partage.classe.nom,
                "transfert_equipe": (reverse("transfert_equipe_grist", args=[partage.classe_id])
                                     + "?" + urlencode({"espace": document})),
                "nom_espace": partage.nom_espace or nom_espace_propose(partage.classe),
                "contenu": contenu if cle != partage.derniere_empreinte else None,
                "icones": icones if contenu and cle != partage.derniere_empreinte else {},
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
    catalogue_modifie = False
    if "editions" in reponse:
        try:
            if not isinstance(reponse["editions"], list):
                raise ValidationError("Index des éditions Grist illisible.")
            editions = referentiels_grist(reponse["editions"])
        except (TypeError, AttributeError, ValidationError):
            return JsonResponse({"erreur": "Index des éditions Grist illisible."}, status=400)
        catalogue_modifie = (partage.editions_catalogue or []) != editions
    mise_a_jour_catalogue = {"editions_catalogue": editions} if "editions" in reponse else {}
    propres = {reference.removeprefix("classe-grist-")
               for reference in classes_grist_locales(partage.classe.ecole)}
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
            nom_espace=partage.nom_espace, derniere_empreinte=partage.derniere_empreinte, **mise_a_jour_catalogue):
        return JsonResponse({"erreur": "L’espace de partage a changé."}, status=409)
    resultat = {"erreurs": erreurs, "nom": partage.nom_espace,
                "partage_confirme": bool(partage.derniere_empreinte)}
    if "editions" in reponse:
        resultat["catalogue_modifie"] = catalogue_modifie
    return JsonResponse(resultat)
