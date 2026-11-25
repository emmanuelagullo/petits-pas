"""Publication directe et choix facultatif de la destination Grist."""
from copy import deepcopy

from django.conf import settings
from django.core.exceptions import ValidationError

from .icones_partagees import externaliser_png
from .identites_referentiels import competences_document
from .models import DestinationPublicationGrist
from .services.catalogues_externes import (
    MODES_CATALOGUE_GRIST, adresse_grist, catalogues_grist_connus, enregistrer_mode_catalogue_grist,
    enregistrer_nom_catalogue_grist, numerotation_grist_globale,
)
from .services.publications_grist import destination_grist, meme_contenu_grist, publier_edition_grist, publier_icones_grist

ACTIONS_GRIST = {"voir-grist", "publier-grist", "enregistrer-mode-grist"}


def historique_grist(request, ecole):
    return DestinationPublicationGrist.objects.filter(ecole=ecole, auteur=request.user).order_by(
        "-publie_le", "-pk"
    )


def presenter_publication_grist(request, classe, contexte, identifiant):
    historique = historique_grist(request, classe.ecole)
    precedente = historique.filter(identifiant_local=identifiant).first()
    destinations = {}
    if precedente:
        destinations[precedente.url] = {"url": precedente.url, "nom": precedente.nom, "espace": precedente.espace}
    for ligne in historique:
        destinations.setdefault(ligne.url, {"url": ligne.url, "nom": ligne.nom, "espace": ligne.espace})
    reglages = classe.ecole.catalogues_referentiels
    for url, catalogue in catalogues_grist_connus(reglages).items():
        if url not in destinations and (reglages.get(url, {}).get("suivis") or reglages.get(url, {}).get("catalogue")):
            destinations[url] = {"url": url, "nom": catalogue["nom"]}
    contexte.update(
        nom_catalogue_propose=f"Catalogue de {classe.ecole.nom}"[:200],
        destinations_grist=list(destinations.values()), derniere_destination=precedente,
        publication_connue=precedente, choix_catalogue_grist=precedente.url if precedente else "",
        modes_catalogue_grist=MODES_CATALOGUE_GRIST,
        modele_grist=getattr(settings, "GRIST_MODELE_URL", ""),
    )


def publication_grist(request, classe, contexte, action, document):
    source = document["source"]
    historique = historique_grist(request, classe.ecole)
    saisie = request.POST.get("url_grist", "").strip()
    choix_catalogue = request.POST.get("destination_grist", "")
    url = saisie or choix_catalogue
    contexte.update(url_grist=url, lien_grist_saisi=saisie,
                    choix_catalogue_grist=choix_catalogue)
    if not url:
        raise ValidationError("Indiquez le lien du catalogue Grist.")
    if len(url) > 2000:
        raise ValidationError("Le lien Grist est trop long.")
    nom_saisi = request.POST.get("nom_catalogue_grist", "").strip()
    contexte["nom_catalogue_saisi"] = nom_saisi
    if len(nom_saisi) > 200:
        raise ValidationError("Le nom du catalogue est limité à 200 caractères.")
    destination = dict(destination_grist(url, preparer_vierge=action == "publier-grist"))
    if destination.get("nom_a_initialiser"):
        destination["nom"] = nom_saisi or contexte["nom_catalogue_propose"]
        if action == "publier-grist":
            destination["nom"] = enregistrer_nom_catalogue_grist(destination["url"], destination["nom"])
    references = {edition["Referentiel"]: edition["Titre"] for edition in destination["editions"]}
    precedente = historique.filter(
        url=destination["url"], identifiant_local=source["identifiant"],
    ).first()
    contexte.update(destination_grist=destination, references_grist=references.items())
    choix = request.POST.get("reference_grist", "")
    contexte["reference_grist"] = choix
    if action == "voir-grist":
        return
    mode = request.POST.get("mode_contenu_grist", "")
    if mode and mode not in MODES_CATALOGUE_GRIST:
        raise ValidationError("Choisissez les contenus du catalogue.")
    if action == "enregistrer-mode-grist":
        if mode:
            enregistrer_mode_catalogue_grist(destination["url"], mode)
            destination.update(mode_contenu=mode, libelle_contenu=MODES_CATALOGUE_GRIST[mode])
            contexte["mode_grist_enregistre"] = True
        return
    mode_effectif = mode or destination.get("mode_contenu", "complet")
    if mode_effectif == "icones":
        ressources = externaliser_png(deepcopy(document))
        if not ressources:
            raise ValidationError("Cochez l’inclusion des icônes ajoutées et vérifiez que le référentiel en contient.")
        prefixe, identifiant = adresse_grist(destination["url"])
        publier_icones_grist(prefixe, identifiant, ressources)
        if mode:
            enregistrer_mode_catalogue_grist(destination["url"], mode)
        contexte["publication_icones_grist"] = {**destination, "nombre": len(ressources)}
        return
    if mode_effectif == "competences":
        document = deepcopy(document)
        for competence in competences_document(document):
            competence.pop("icone_png", None)
    reference = precedente.reference if precedente else source["identifiant"]
    if choix == "nouveau":
        reference = source["identifiant"]
    elif choix:
        if choix not in references:
            raise ValidationError("Le référentiel choisi ne figure plus dans ce catalogue.")
        reference = choix
    if precedente and not choix and reference not in references:
        raise ValidationError("Le référentiel publié précédemment est introuvable. Choisissez comment publier.")
    editions = [e for e in destination["editions"] if e["Referentiel"] == reference]
    derniere = max(editions, key=lambda e: e["Numero"], default=None)
    nouvelle_edition = bool(choix and choix != "nouveau") or bool(precedente and not choix)
    identique = derniere and meme_contenu_grist(derniere, document)
    if derniere and not nouvelle_edition and not identique:
        raise ValidationError("Cet identifiant existe déjà. Choisissez ce référentiel pour ajouter une édition.")
    titre = references.get(reference, source["titre"])
    if identique:
        numero = derniere["Numero"]
    else:
        perimetre = destination["editions"] if numerotation_grist_globale(destination["editions"]) else editions
        numero = max((e["Numero"] for e in perimetre), default=0) + 1
        publier_edition_grist(destination, reference, titre, numero, document)
    if mode:
        enregistrer_mode_catalogue_grist(destination["url"], mode)
    DestinationPublicationGrist.objects.update_or_create(
        ecole=classe.ecole, auteur=request.user, classe=classe, url=destination["url"],
        identifiant_local=source["identifiant"],
        defaults={"nom": destination["nom"], "espace": destination["espace"], "reference": reference},
    )
    contexte.pop("url_grist", None)
    contexte.pop("destination_grist", None)
    contexte.pop("lien_grist_saisi", None)
    contexte["publication_grist_reussie"] = {**destination, "numero": numero, "identique": identique}
