"""Choix et confirmation de la destination d’une édition de classe."""
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError

from .models import DestinationPublicationGrist
from .services.publications_grist import destination_grist, publier_edition_grist

ACTIONS_GRIST = {"destination-grist", "apercu-grist-classe", "publier-grist"}
SEL = "destination-publication-grist"


def publication_grist(request, classe, contexte, action, document):
    historique = DestinationPublicationGrist.objects.filter(ecole=classe.ecole, auteur=request.user).order_by(
        "-publie_le", "-pk"
    )
    source = document["source"]
    destinations = {}
    for ligne in historique:
        destinations.setdefault(ligne.url, ligne)
    contexte.update(
        destinations_grist=list(destinations.values()),
        derniere_destination=next(iter(destinations.values()), None),
        modele_grist=getattr(settings, "GRIST_MODELE_URL", ""),
        formulaire_grist=True,
    )
    url = request.POST.get("url_grist", "").strip() or request.POST.get("destination_grist", "")
    if action == "publier-grist":
        try:
            choix = signing.loads(request.POST.get("jeton_destination", ""), salt=SEL, max_age=1800)
        except signing.BadSignature as erreur:
            raise ValidationError("Examinez de nouveau la destination de publication.") from erreur
        if choix["partage"] != contexte["jeton_partage"]:
            raise ValidationError("Le référentiel préparé a changé. Examinez de nouveau la destination.")
        contexte.update(confirmation_grist=choix, jeton_destination=request.POST["jeton_destination"])
        destination = destination_grist(choix["url"])
        if (destination["nom"], destination["espace"]) != (choix["nom"], choix["espace"]):
            raise ValidationError("La destination a changé. Examinez-la de nouveau.")
        publier_edition_grist(destination, choix["reference"], choix["titre"], choix["numero"], document)
        DestinationPublicationGrist.objects.update_or_create(
            ecole=classe.ecole, auteur=request.user, classe=classe, url=destination["url"],
            identifiant_local=source["identifiant"],
            defaults={"nom": destination["nom"], "espace": destination["espace"], "reference": choix["reference"]},
        )
        contexte["publication_grist_reussie"] = choix
        return
    if not url and contexte["derniere_destination"]:
        url = contexte["derniere_destination"].url
    if not url:
        return
    if len(url) > 2000:
        raise ValidationError("Le lien Grist est trop long.")
    contexte["url_grist"] = url
    destination = destination_grist(url)
    references = {}
    for edition in destination["editions"]:
        references[edition["Referentiel"]] = edition["Titre"]
    precedente = historique.filter(classe=classe, url=destination["url"], identifiant_local=source["identifiant"]).first()
    defaut = precedente.reference if precedente and precedente.reference in references else ""
    contexte.update(destination_grist=destination, references_grist=references.items(), reference_grist=defaut)
    if action != "apercu-grist-classe":
        return
    reference = request.POST.get("reference_grist", "")
    titre = source["titre"]
    if reference:
        if reference not in references:
            raise ValidationError("Ce référentiel ne figure plus dans le document choisi.")
        titre = references[reference]
    else:
        reference = source["identifiant"]
        if reference in references:
            raise ValidationError("Cet identifiant est déjà utilisé. Choisissez une nouvelle édition ou changez l’identifiant.")
    numero = max((edition["Numero"] for edition in destination["editions"]), default=0) + 1
    choix = {cle: destination[cle] for cle in ("url", "nom", "espace")}
    choix.update(partage=contexte["jeton_partage"], reference=reference, titre=titre, numero=numero,
                 nouvelle_edition=reference in references)
    contexte["confirmation_grist"] = choix
    contexte["jeton_destination"] = signing.dumps(choix, salt=SEL)
