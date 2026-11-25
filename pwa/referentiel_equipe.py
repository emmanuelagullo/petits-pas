"""Éditions d'équipe synchronisées par la PWA, séparées des projections de classe."""
import json

import yaml
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from suivi.autorisations import GERER_REFERENTIEL_CLASSE, charger_classe_autorisee
from suivi.contexte_ecole import ecole_courante
from suivi.models import Classe, ContributionReferentielEquipe, PartageGristClasse, ReceptionReferentielGrist
from suivi.services.catalogues_externes import HOTE_GRIST, TAILLE_MAX, adresse_grist
from suivi.services.publications_grist import contenu_grist
from suivi.services.edition_referentiel_equipe import modifier_edition_equipe, rubriques_equipe
from suivi.services.import_sources_referentiels import importer_source, normaliser
from suivi.services.apercu_mises_a_jour import definitions_document
from suivi.services.journal_referentiel_equipe import (
    contribution, fusionner_tetes, identifiant_contribution, terminaisons, verifier_contribution,
)
from suivi.services.paquets_referentiels import MAX_ARCHIVE, empaqueter, lire_paquet
from .partage_grist import document_projection, partage_local
from suivi.views import acces_requis
from suivi.views_paquets_referentiels import telecharger_paquet


def espace_et_journal(request, pk):
    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    if classe.etat != Classe.ACTIVE:
        raise Http404
    if settings.MODE_LOCAL or getattr(settings, "MODE_PWA", False):
        partage = PartageGristClasse.objects.filter(classe=classe, actif=True).first()
        if partage is None:
            raise Http404
        _, document_grist = adresse_grist(partage.url)
    else:
        # Le journal serveur est partagé dans la base de l'école.
        document_grist = ""
    journal = ContributionReferentielEquipe.objects.filter(ecole=ecole, document_grist=document_grist)
    return classe, journal, {"ecole": ecole, "document_grist": document_grist}


def enregistrer(journal, perimetre, edition, identifiant, *, envoyee=False):
    verifier_contribution(identifiant, edition)
    objet, _ = journal.get_or_create(**perimetre, empreinte=identifiant, defaults={"edition": edition, "envoyee": envoyee})
    if envoyee and not objet.envoyee:
        journal.filter(pk=objet.pk).update(envoyee=True)


@partage_local
@acces_requis
@require_http_methods(["GET", "POST"])
def transfert(request, pk):
    _, journal, perimetre = espace_et_journal(request, pk)
    if request.GET.get("espace") != perimetre["document_grist"]:
        return JsonResponse({"erreur": "L’espace de partage a changé."}, status=409)
    if request.method == "GET":
        return JsonResponse({
            "connues": list(journal.values_list("empreinte", flat=True)),
            "a_envoyer": list(journal.filter(envoyee=False).order_by("pk").values("empreinte", "edition")[:1]),
        })
    if len(request.body) > 4 * TAILLE_MAX:
        return JsonResponse({"erreur": "Contribution trop volumineuse."}, status=400)
    try:
        donnees = json.loads(request.body)
        enregistrer(journal, perimetre, donnees["edition"], donnees["empreinte"], envoyee=True)
    except (KeyError, TypeError, ValueError, ValidationError):
        return JsonResponse({"erreur": "Contribution d’équipe illisible."}, status=400)
    return JsonResponse({"ok": True})


@acces_requis
@require_http_methods(["GET", "POST"])
def espace(request, pk):
    classe, journal, perimetre = espace_et_journal(request, pk)
    editions = dict(journal.values_list("empreinte", "edition"))
    erreur = ""
    conflits = []
    tetes = []
    try:
        tetes = terminaisons(editions)
        if request.method == "GET" and request.GET.get("edition") in tetes:
            document = editions[request.GET["edition"]]["document"]
            return telecharger_paquet(empaqueter(document), document["source"]["titre"],
                                      edition=document["version"])
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "preparer-publication-grist":
                partage = PartageGristClasse.objects.filter(classe=classe, actif=True).first()
                if not perimetre["document_grist"] or not partage:
                    raise ValidationError("Cette classe ne participe pas à un espace Grist.")
                if len(tetes) != 1 or request.POST.get("edition") != tetes[0]:
                    raise ValidationError("L’édition d’équipe a changé. Rechargez cette page.")
                if not journal.filter(empreinte=tetes[0], envoyee=True).exists():
                    raise ValidationError("Synchronisez l’édition d’équipe depuis l’espace de partage.")
                prefixe, identifiant = adresse_grist(partage.url)
                if identifiant != perimetre["document_grist"]:
                    raise ValidationError("L’espace de partage a changé. Rechargez cette page.")
                document, _ = normaliser(editions[tetes[0]]["document"])
                reference = "equipe-grist-" + identifiant
                document["source"]["identifiant"] = reference
                # La contribution détermine le contenu, indépendamment du numéro
                # d’édition attribué au moment de publier dans le catalogue.
                document["version"] = tetes[0]
                return JsonResponse({
                    "api": f"https://{HOTE_GRIST}{prefixe}/api/docs/{identifiant}",
                    "reference": reference, "titre": document["source"]["titre"],
                    "contenu": contenu_grist(document),
                })
            if action == "catalogue":
                if len(tetes) != 1 or request.POST.get("edition") != tetes[0]:
                    raise ValidationError("Réunissez les contributions avant d’ajouter cette édition au catalogue.")
                document = editions[tetes[0]]["document"]
                document_grist = perimetre["document_grist"]
                reference = "equipe-grist-" + document_grist if document_grist else "equipe-ecole"
                document = {**document, "version": tetes[0],
                            "source": {**document["source"], "identifiant": reference, "provisoire": True}}
                version, _, _ = importer_source(yaml.safe_dump(document, allow_unicode=True), ecole=classe.ecole)
                if document_grist:
                    ReceptionReferentielGrist.objects.get_or_create(source=version.source, document_grist=document_grist)
                messages.success(request, "Édition ajoutée au catalogue de l’école. La classe conserve son référentiel.")
                return redirect("referentiel_equipe_grist", pk=pk)
            parents = request.POST.getlist("parent")
            if action == "initialiser":
                if editions:
                    raise ValidationError("Un référentiel d’équipe est déjà disponible. Rechargez la page.")
                document = document_projection(classe, "equipe")
                document_grist = perimetre["document_grist"]
                reference = "equipe-grist-" + document_grist if document_grist else "equipe-ecole"
                document["source"].update(identifiant=reference,
                                          titre=f"Référentiel d’équipe de {classe.ecole.nom}"[:200])
                document["version"] = "initiale"
                edition = contribution((), document)
            elif action in ("fusionner", "resoudre-conflits"):
                if parents != tetes[:2] or len(parents) != 2:
                    raise ValidationError("Les contributions ont changé. Relisez les versions reçues.")
                edition, conflits = fusionner_tetes(editions, *parents)
                if conflits and action == "resoudre-conflits":
                    choix = {conflit.chemin: request.POST.get(f"conflit-{i}")
                             for i, conflit in enumerate(conflits, start=1)}
                    if any(cote not in ("locale", "distante") for cote in choix.values()):
                        return render_espace(request, classe, editions, tetes,
                                             erreur="Choisissez une version pour chaque différence.", conflits=conflits)
                    edition, conflits = fusionner_tetes(editions, *parents, choix=choix)
                if conflits:
                    return render_espace(request, classe, editions, tetes, conflits=conflits)
            elif action in ("ajouter-competence", "modifier-competence", "retirer-competence"):
                if len(parents) != 1 or parents[0] not in editions:
                    raise ValidationError("La version de départ n’est plus disponible.")
                document = modifier_edition_equipe(editions[parents[0]]["document"], action, request.POST)
                if document == editions[parents[0]]["document"]:
                    return redirect("referentiel_equipe_grist", pk=pk)
                edition = contribution(parents, document)
            else:
                if action == "ajouter" and request.POST.get("resoudre") == "oui":
                    if (len(tetes) < 2 or request.POST.getlist("tete") != tetes[:2]
                            or len(parents) != 1 or parents[0] not in tetes[:2]):
                        raise ValidationError("Les contributions ont changé. Relisez les versions reçues.")
                    parents = tetes[:2]
                elif action != "ajouter" or (len(parents) != 1 and (parents or editions)):
                    raise ValidationError("Choisissez la version qui a servi de base à votre modification.")
                if any(parent not in editions for parent in parents):
                    raise ValidationError("La version de départ n’est plus disponible.")
                fichier = request.FILES.get("paquet")
                if not fichier:
                    raise ValidationError("Choisissez un ZIP de référentiel.")
                document = yaml.safe_load(lire_paquet(fichier.read(MAX_ARCHIVE + 1)))
                identifiant_source = document.get("source", {}).get("identifiant")
                if any(identifiant_source != editions[parent]["document"]["source"]["identifiant"] for parent in parents):
                    raise ValidationError("Le référentiel du ZIP diffère de celui de la version de départ.")
                edition = contribution(parents, document)
            if len(json.dumps(edition, ensure_ascii=False).encode()) > TAILLE_MAX:
                raise ValidationError("L’édition d’équipe est trop volumineuse.")
            enregistrer(journal, perimetre, edition, identifiant_contribution(edition))
            return redirect("referentiel_equipe_grist", pk=pk)
    except (ValidationError, KeyError, TypeError) as cause:
        erreur = " ".join(cause.messages) if isinstance(cause, ValidationError) else "Édition illisible."
        if request.method == "POST" and request.POST.get("action") == "preparer-publication-grist":
            return JsonResponse({"erreur": erreur}, status=400)
    return render_espace(request, classe, editions, tetes, erreur=erreur, conflits=conflits)


def render_espace(request, classe, editions, tetes, *, erreur="", conflits=()):
    apercus = []
    for cle in tetes:
        document = editions[cle]["document"]
        contenu, _ = normaliser(document)
        apercus.append((cle, document, [{**ligne, "reference": reference}
                                       for reference, ligne in definitions_document(contenu).items()]))
    return render(request, "suivi/referentiel_equipe_grist.html", {
        "classe": classe, "tetes": apercus, "a_reunir": tetes[:2] if len(tetes) >= 2 else [],
        "edition_unique": tetes[0] if len(tetes) == 1 else "",
        "rubriques_edition": ([(cle, nom) for cle, nom, _ in rubriques_equipe(editions[tetes[0]]["document"])]
                              if len(tetes) == 1 else []),
        "niveaux": ("PS", "MS", "GS"),
        "reference_editee": request.POST.get("reference", "") if erreur else "",
        "saisie_libelle": request.POST.get("libelle", ""),
        "saisie_niveau": request.POST.get("niveau", ""),
        "editions": [(cle, edition["document"]) for cle, edition in editions.items()],
        "erreur": erreur, "conflits": conflits,
        "choix_conflits": bool(conflits) and all(c.chemin[-1] != "emplacement" for c in conflits),
    }, status=400 if erreur else 200)
