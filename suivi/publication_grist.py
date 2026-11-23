"""Publication directe et choix facultatif de la destination Grist."""
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import DestinationPublicationGrist
from .services.publications_grist import contenu_grist, destination_grist, publier_edition_grist

ACTIONS_GRIST = {"voir-grist", "publier-grist"}


def historique_grist(request, classe):
    return DestinationPublicationGrist.objects.filter(ecole=classe.ecole, auteur=request.user).order_by(
        "-publie_le", "-pk"
    )


def presenter_publication_grist(request, classe, contexte, identifiant):
    historique = historique_grist(request, classe)
    destinations = {}
    for ligne in historique:
        destinations.setdefault(ligne.url, ligne)
    derniere = next(iter(destinations.values()), None)
    precedente = historique.filter(classe=classe, url=derniere.url, identifiant_local=identifiant).first() if derniere else None
    contexte.update(
        destinations_grist=list(destinations.values()), derniere_destination=derniere,
        publication_connue=precedente, modele_grist=getattr(settings, "GRIST_MODELE_URL", ""),
    )


def publication_grist(request, classe, contexte, action, document):
    source = document["source"]
    historique = historique_grist(request, classe)
    url = request.POST.get("url_grist", "").strip() or request.POST.get("destination_grist", "")
    contexte["url_grist"] = url
    if not url:
        raise ValidationError("Indiquez le lien du document Grist.")
    if len(url) > 2000:
        raise ValidationError("Le lien Grist est trop long.")
    destination = destination_grist(url)
    references = {edition["Referentiel"]: edition["Titre"] for edition in destination["editions"]}
    precedente = historique.filter(
        classe=classe, url=destination["url"], identifiant_local=source["identifiant"],
    ).first()
    contexte.update(destination_grist=destination, references_grist=references.items())
    choix = request.POST.get("reference_grist", "")
    contexte["reference_grist"] = choix
    if action == "voir-grist":
        return
    reference = precedente.reference if precedente else source["identifiant"]
    if choix == "nouveau":
        reference = source["identifiant"]
    elif choix:
        if choix not in references:
            raise ValidationError("Le référentiel choisi ne figure plus dans ce document.")
        reference = choix
    if precedente and not choix and reference not in references:
        raise ValidationError("Le référentiel publié précédemment est introuvable. Choisissez comment publier.")
    editions = [e for e in destination["editions"] if e["Referentiel"] == reference]
    derniere = max(editions, key=lambda e: e["Numero"], default=None)
    nouvelle_edition = bool(choix and choix != "nouveau") or bool(precedente and not choix)
    identique = derniere and derniere.get("Contenu") == contenu_grist(document)
    if derniere and not nouvelle_edition and not identique:
        raise ValidationError("Cet identifiant existe déjà. Choisissez ce référentiel pour ajouter une édition.")
    titre = references.get(reference, source["titre"])
    if identique:
        numero = derniere["Numero"]
    else:
        numero = max((e["Numero"] for e in destination["editions"]), default=0) + 1
        publier_edition_grist(destination, reference, titre, numero, document)
    DestinationPublicationGrist.objects.update_or_create(
        ecole=classe.ecole, auteur=request.user, classe=classe, url=destination["url"],
        identifiant_local=source["identifiant"],
        defaults={"nom": destination["nom"], "espace": destination["espace"], "reference": reference},
    )
    contexte.pop("url_grist", None)
    contexte.pop("destination_grist", None)
    contexte["publication_grist_reussie"] = {**destination, "numero": numero, "identique": identique}
