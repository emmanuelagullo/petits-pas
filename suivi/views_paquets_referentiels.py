"""Diffusion des éditions publiques accessibles dans le contexte courant."""
from hashlib import sha256

import yaml
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string, salted_hmac
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, IMPORTER_REFERENTIEL_ECOLE, VOIR_SUIVI,
                            autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .forms_referentiels import PartageReferentielClasseForm
from .identites_referentiels import competences_document, identifiant_source_ecole
from .models import AdoptionReferentiel, BrouillonReferentiel, ChoixApplicationAnnuel, Classe, Ecole, InformationsPartageReferentielClasse, SourceReferentiel, VersionReferentiel, annee_scolaire_pour
from .navigation import lien
from .presentation import catalogue_icones
from .referentiels import adoption_courante
from .publication_grist import ACTIONS_GRIST, presenter_publication_grist, publication_grist
from .services.apercu_mises_a_jour import comparer_documents, definitions_document
from .services.choix_bases_referentiels import choix_bases, publier_choix_application
from .services.composition_referentiels import catalogue_composition, composer_paquet
from .services.catalogues_externes import edition_grist
from .services.import_sources_referentiels import importer_source, lire_source
from .services.paquets_referentiels import MAX_ARCHIVE, empaqueter, exporter_paquet, exporter_selection, lire_paquet
from .services.partage_referentiel_classe import preparer_referentiel_classe
from .views import acces_requis

SEL = "diffusion-referentiel"
SEL_PUBLICATION = "publication-referentiel"


def telecharger_paquet(donnees):
    reponse = HttpResponse(donnees, content_type="application/zip")
    reponse["Content-Disposition"] = 'attachment; filename="referentiel.zip"'
    return reponse


def publication(request, contexte, engagement):
    annee = contexte["annee"]
    politique = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee).first()
    autorisees = set(politique.versions_autorisees.values_list("pk", flat=True)) if politique else set()
    proposee = politique.version_proposee_id if politique else None
    revision = politique.revision if politique else 0
    editions = VersionReferentiel.objects.filter(source__ecole__isnull=True,
        contenu__origine="source_declaree").exclude(pk__in=autorisees).select_related("source")
    contexte["a_publier"] = editions
    contexte["jeton_publication"] = signing.dumps({**engagement, "revision": revision}, salt=SEL_PUBLICATION)
    if request.method != "POST" or request.POST.get("action") != "publier":
        return
    try:
        attendu = signing.loads(request.POST.get("jeton_publication", ""), salt=SEL_PUBLICATION, max_age=1800)
        edition = editions.get(pk=int(request.POST.get("publier_edition", "")))
    except (signing.BadSignature, ValueError, VersionReferentiel.DoesNotExist) as erreur:
        raise ValidationError("Choisissez de nouveau une édition à publier.") from erreur
    if attendu != {**engagement, "revision": revision}:
        raise ValidationError("La publication a changé. Relisez les choix de l’année.")
    publier_choix_application(annee=annee, versions_ids=sorted(autorisees | {edition.pk}),
        proposee_id=proposee or edition.pk, revision_attendue=revision)
    contexte["message"] = "Édition autorisée pour l’année. Les classes conservent leur base."
    contexte.pop("a_publier", None)



def brouillon_composition(request, ecole, annee, contexte, action):
    perimetre = BrouillonReferentiel.objects.filter(ecole=ecole, auteur=request.user, annee_scolaire=annee)
    enregistre = perimetre.first()
    revision = enregistre.revision if enregistre else 0
    cle = f"composition:{request.user.pk}:{ecole.pk}:{annee}"
    brouillon = enregistre.contenu if enregistre else request.session.get(cle, {})
    contexte.update(brouillon_composition=brouillon, revision_brouillon=revision,
                    composition_ouverte=bool(brouillon))
    if action in ("composer", "enregistrer_composition", "ajouter_ligne_composition"):
        champs = ("titre", "identifiant", "version", "provenance", "licence", "rubrique",
                  "nouvelle", "identite_nouvelle", "niveau_nouvelle")
        brouillon = {champ: request.POST.get(champ, "") for champ in champs}
        brouillon["reprises"] = request.POST.getlist("reprise")
        colonnes = ("rubrique", "libelle", "identite", "niveau")
        listes = [request.POST.getlist(f"creation_{champ}") for champ in colonnes]
        if len({len(liste) for liste in listes}) != 1 or len(listes[0]) > 50:
            raise ValidationError("Le formulaire de composition a changé. Rechargez le brouillon.")
        brouillon["creations"] = [dict(zip(colonnes, valeurs)) for valeurs in zip(*listes)]
        if action == "ajouter_ligne_composition" and len(brouillon["creations"]) < 50:
            brouillon["creations"].append({"niveau": "PS"})
        if request.POST.get("revision_brouillon", "0") != str(revision):
            raise ValidationError("Le brouillon a changé. Relisez la version enregistrée avant de modifier la composition.")
        if enregistre:
            if not perimetre.filter(revision=revision).update(contenu=brouillon, revision=revision + 1):
                raise ValidationError("Le brouillon a changé. Rechargez la page.")
        else:
            BrouillonReferentiel.objects.create(ecole=ecole, auteur=request.user, annee_scolaire=annee,
                                                contenu=brouillon)
        revision += 1
        request.session.pop(cle, None)
    contexte["brouillon_composition"] = brouillon
    contexte["revision_brouillon"] = revision
    contexte["composition_ouverte"] = bool(brouillon) or action in (
        "composer", "enregistrer_composition", "ajouter_ligne_composition")
    return brouillon


def lignes_selection(versions, *, avec_source=False):
    lignes = []
    for version in versions:
        for reference, competence in definitions_document(version.contenu).items():
            lignes.append({**competence,
                "reference": f"{version.pk}:{reference}" if avec_source else reference,
                "edition": f"{version.source.titre} — {version.numero}" if avec_source else "",
            })
    return lignes


def apercu_document(document, ecole):
    contenu, _ = lire_source(document)
    identifiant = contenu["source"]["identifiant"]
    if ecole is not None:
        identifiant = identifiant_source_ecole(ecole, identifiant)
    precedente = VersionReferentiel.objects.filter(source__identifiant=identifiant, source__ecole=ecole
        ).exclude(numero=contenu["version"]).order_by("-pk").first()
    competences = list(competences_document(contenu))
    icones = catalogue_icones()
    return {
        "apercu": contenu,
        "comparaison_import": comparer_documents(precedente.contenu, contenu) if precedente else None,
        "edition_comparee": precedente.numero if precedente else None,
        "destination_import": "de l’école" if ecole else "de l’application",
        "competences_importees": competences,
        "icones_importees": [icones[cle] for cle in sorted({c["icone"] for c in competences if c["icone"]})],
    }


ACTIONS_DIRECTES_PARTAGE = {"apercu-classe", "telecharger-classe", "enregistrer-partage"} | ACTIONS_GRIST
ACTIONS_PARTAGE = ACTIONS_DIRECTES_PARTAGE | {"exporter-classe"}


def informations_partage(classe, adoption):
    source = adoption.version.source
    enregistrees = InformationsPartageReferentielClasse.objects.filter(classe=classe).first()
    if enregistrees:
        return enregistrees.donnees, enregistrees.adoption_id != adoption.pk
    identifiant = salted_hmac("referentiel-partage-classe", str(classe.pk), algorithm="sha256").hexdigest()
    licence = source.licence
    if licence.casefold() in {"non renseignée", "non renseigné", "inconnue"}:
        licence = ""
    return {
        "titre": f"Référentiel de {classe.nom}",
        "identifiant": f"classe-{identifiant}",
        "version": "1",
        "provenance": f"Dérivé de {source.titre}, édition {adoption.version.numero}. {source.provenance}"[:4000],
        "licence": licence,
    }, False


def partage_classe(request, classe, contexte, action):
    adoption = adoption_courante(classe)
    if not adoption or adoption.clos or classe.etat != Classe.ACTIVE:
        contexte["partage_classe_indisponible"] = (
            "La classe doit être active et avoir une base adoptée, ouverte au suivi."
        )
        if action in ACTIONS_PARTAGE:
            raise ValidationError("Cette classe ne dispose pas d’une base courante à partager.")
        return
    initial, base_changee = informations_partage(classe, adoption)
    contexte.update(base_du_partage=adoption.version, informations_partage=initial,
                    modifier_partage=base_changee or not initial["licence"])
    direct = action in ACTIONS_DIRECTES_PARTAGE
    formulaire = PartageReferentielClasseForm(request.POST if direct and "titre" in request.POST else None,
                                              initial=initial)
    contexte["partage_classe"] = formulaire
    presenter_publication_grist(request, classe, contexte, initial["identifiant"])
    if action not in ACTIONS_PARTAGE:
        return
    contexte["volet"] = "exporter"
    engagement = {"auteur": request.user.pk, "adoption": adoption.pk}
    if direct:
        if formulaire.is_bound and not formulaire.is_valid():
            contexte["modifier_partage"] = True
            return
        donnees = formulaire.cleaned_data if formulaire.is_bound else initial
        formulaire = PartageReferentielClasseForm(donnees)
        contexte["partage_classe"] = formulaire
        if not formulaire.is_valid() or (base_changee and "titre" not in request.POST):
            contexte["modifier_partage"] = True
            return
        donnees = formulaire.cleaned_data
    else:
        try:
            preparation = signing.loads(request.POST.get("jeton_partage", ""), salt="partage-referentiel-classe",
                                        max_age=1800)
        except signing.BadSignature as erreur:
            raise ValidationError("Réessayez de partager le référentiel.") from erreur
        if preparation["engagement"] != engagement:
            raise ValidationError("La base de la classe a changé. Reprenez le partage du référentiel.")
        donnees = preparation["donnees"]
    contexte["informations_partage"] = donnees
    document = preparer_referentiel_classe(classe, {k: v for k, v in donnees.items() if k != "version"}, donnees["version"])
    empreinte = sha256(yaml.safe_dump(document, allow_unicode=True).encode()).hexdigest()
    if not direct and empreinte != preparation["empreinte"]:
        raise ValidationError("Le référentiel a changé. Examinez de nouveau le contenu à partager.")
    origines = {c["source_origine"] for c in competences_document(document) if c.get("source_origine")}
    sources = SourceReferentiel.objects.filter(
        Q(ecole=classe.ecole, identifiant_diffusion__in=origines) | Q(ecole__isnull=True, identifiant__in=origines)
    )
    licences = sorted(set(sources.values_list("licence", flat=True)) | {adoption.version.source.licence})
    if direct and not request.POST.get("titre") and any(licence != donnees["licence"] for licence in licences):
        if not InformationsPartageReferentielClasse.objects.filter(
            classe=classe, adoption=adoption, donnees=donnees, licences_sources=licences,
        ).exists():
            contexte["modifier_partage"] = True
            return
    contexte["modifier_partage"] = False
    enregistrement = {"donnees": donnees, "adoption": adoption, "licences_sources": licences}
    paquet = empaqueter(document)
    if action in ("telecharger-classe", "exporter-classe"):
        InformationsPartageReferentielClasse.objects.update_or_create(
            classe=classe, defaults=enregistrement,
        )
        return telecharger_paquet(paquet)
    if action == "enregistrer-partage":
        InformationsPartageReferentielClasse.objects.update_or_create(classe=classe, defaults=enregistrement)
        presenter_publication_grist(request, classe, contexte, donnees["identifiant"])
        return
    normalise, _ = lire_source(lire_paquet(paquet))
    if action in ACTIONS_GRIST:
        try:
            publication_grist(request, classe, contexte, action, normalise)
        except ValidationError as erreur:
            contexte["erreur_grist"] = " ".join(erreur.messages)
        if contexte.get("publication_grist_reussie"):
            InformationsPartageReferentielClasse.objects.update_or_create(classe=classe, defaults=enregistrement)
            presenter_publication_grist(request, classe, contexte, donnees["identifiant"])
        return
    lignes = []
    for domaine in normalise["domaines"]:
        for groupe in [domaine, *domaine["sous_domaines"]]:
            rubrique = domaine["nom"] if groupe is domaine else f'{domaine["nom"]} / {groupe["nom"]}'
            lignes.extend({**competence, "rubrique": rubrique} for competence in groupe["competences"])
    contexte["apercu_partage"] = {
        "apercu": normalise, "competences_importees": lignes,
        "icones_importees": [catalogue_icones()[cle] for cle in sorted({
            c["icone"] for c in competences_document(normalise) if c["icone"]
        })],
    }
    if direct:
        contexte["jeton_partage"] = signing.dumps(
            {"engagement": engagement, "donnees": donnees, "empreinte": empreinte},
            salt="partage-referentiel-classe",
        )
    else:
        contexte["jeton_partage"] = request.POST["jeton_partage"]



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
    action = request.POST.get("action") if request.method == "POST" else None
    peut_importer_ecole = autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, classe or ecole)
    peut_gerer_ecole = autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole)
    contexte = {"classe": classe, "annee": annee, "volet": request.GET.get("volet"), "peut_importer": peut_importer_ecole or request.user.is_superuser,
                "peut_importer_global": request.user.is_superuser}
    if classe and peut_gerer_ecole and request.GET.get("depuis") == "export-ecole":
        contexte["retour_export_ecole"] = lien(
            "paquets_referentiels_ecole", annee=annee, volet="exporter", ancre="export-referentiel",
        )
    if classe is None and request.GET.get("origine") == "decouverte":
        contexte["retour_decouverte"] = lien(
            "decouvrir_referentiels", annee=annee, q=request.GET.get("q", "")[:200],
            filtre=request.GET.get("filtre", "")[:32],
            **({"depuis": "echange"} if request.GET.get("depuis") == "echange" else {}),
        )
    try:
        if classe is not None:
            resultat = partage_classe(request, classe, contexte, action)
            if resultat:
                return resultat
            if action in ACTIONS_PARTAGE:
                action = None
        versions = {str(v.pk): v for v in choix_bases(ecole, annee).versions if v.contenu.get("origine") == "source_declaree"}
        edition = request.GET.get("edition")
        if edition is None and classe is not None:
            adoption = adoption_courante(classe)
            edition = str(adoption.version_id) if adoption else None
        version = versions.get(edition)
        if version:
            contexte["edition"] = version
            contexte["competences"] = lignes_selection([version])
        if classe is None:
            contexte["classes_partage"] = [
                (adoption.classe.nom, lien("paquets_referentiels_classe", adoption.classe_id,
                                         volet="exporter", depuis="export-ecole", ancre="export-referentiel"))
                for adoption in AdoptionReferentiel.objects.filter(
                    classe__ecole=ecole, classe__annee_scolaire=annee, classe__etat=Classe.ACTIVE,
                    courante=True, clos=False,
                ).select_related("classe").order_by("classe__nom", "classe_id")
                if autorise(request.user, GERER_REFERENTIEL_CLASSE, adoption.classe)
            ]
            catalogue = catalogue_composition(versions.values())
            contexte["catalogue_composition"] = lignes_selection(versions.values(), avec_source=True)
            brouillon = brouillon_composition(request, ecole, annee, contexte, action)
            if action == "composer":
                return telecharger_paquet(composer_paquet(
                    catalogue, brouillon, brouillon["reprises"], brouillon["creations"]))
            if action in ("enregistrer_composition", "ajouter_ligne_composition"):
                contexte["message"] = "Brouillon enregistré pour cette année."
                action = None
        engagement = {"auteur": request.user.pk, "ecole": ecole.pk, "classe": classe_pk, "annee": annee}
        if action == "publier" and (not request.user.is_superuser or classe is not None):
            raise PermissionDenied
        if request.user.is_superuser and classe is None:
            publication(request, contexte, engagement)
        if action and action != "publier":
            if action in ("edition", "selection"):
                if version is None:
                    raise PermissionDenied
                donnees = (exporter_paquet(version) if action == "edition" else
                           exporter_selection(version, request.POST.getlist("competence")))
                return telecharger_paquet(donnees)
            if not contexte["peut_importer"]:
                raise PermissionDenied
            if action == "importer":
                try:
                    attendu = signing.loads(request.POST.get("jeton", ""), salt=SEL, max_age=1800)
                except signing.BadSignature as erreur:
                    raise ValidationError("Préparez de nouveau l’aperçu du fichier.") from erreur
                preparation = request.session.get(SEL)
                if not preparation or attendu != preparation["jeton"] or any(
                    attendu.get(cle) != valeur for cle, valeur in engagement.items()
                ):
                    raise ValidationError("La préparation ou son contexte a changé. Examinez de nouveau le fichier.")
                if attendu["global"] and not request.user.is_superuser:
                    raise PermissionDenied
                with transaction.atomic():
                    if not attendu["global"]:
                        ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
                        if classe is not None:
                            classe = Classe.objects.select_related("ecole").get(pk=classe.pk, ecole=ecole)
                        if not autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, classe or ecole):
                            raise PermissionDenied
                    edition_importee, cree, _ = importer_source(
                        preparation["document"], ecole=None if attendu["global"] else ecole)
                if not attendu["global"]:
                    candidates = [classe] if classe else [
                        c for c in ecole.classes.filter(annee_scolaire=annee).exclude(etat=Classe.ARCHIVEE)
                        if autorise(request.user, GERER_REFERENTIEL_CLASSE, c)
                    ]
                    edition_autorisee = edition_importee in choix_bases(ecole, annee).versions
                    contexte["edition_autorisee"] = edition_autorisee
                    contexte["edition_a_autoriser"] = not edition_autorisee
                    if not edition_autorisee and peut_gerer_ecole:
                        contexte["autoriser_edition_url"] = (
                            reverse("referentiels_ecole") + f"?annee={annee}#choix-ecole"
                        )
                    if edition_autorisee and len(candidates) == 1 and candidates[0].etat != Classe.ARCHIVEE:
                        cible_classe = candidates[0]
                        adoption = adoption_courante(cible_classe)
                        if (adoption and not adoption.clos and adoption.version_id != edition_importee.pk
                                and autorise(request.user, VOIR_SUIVI, cible_classe)):
                            contexte["lien_reprise"] = (
                                reverse("catalogue_competences", args=[cible_classe.pk]) +
                                f"?source=version-{edition_importee.pk}"
                            )
                        if not adoption or not adoption.clos:
                            contexte["lien_adoption"] = (
                                reverse("referentiel_classe", args=[cible_classe.pk]) +
                                f"?edition={edition_importee.pk}#choisir-referentiel"
                            )
                request.session.pop(SEL, None)
                cible = "de l’application" if attendu["global"] else "de l’école"
                contexte["message"] = (f"Édition ajoutée au catalogue {cible}." if cree else
                                       f"Cette édition figure déjà dans le catalogue {cible}.")
            elif action in ("apercu", "apercu-grist"):
                global_ = action == "apercu" and request.POST.get("destination") == "application"
                if (global_ and not request.user.is_superuser) or (not global_ and not peut_importer_ecole):
                    raise PermissionDenied
                if action == "apercu-grist":
                    if classe is not None:
                        raise PermissionDenied
                    try:
                        numero = int(request.POST.get("numero", ""))
                    except ValueError as erreur:
                        raise ValidationError("Choisissez une édition Grist à examiner.") from erreur
                    document = edition_grist(request.POST.get("catalogue", ""), request.POST.get("reference"), numero)
                else:
                    fichier = request.FILES.get("paquet")
                    if not fichier:
                        raise ValidationError("Choisissez le fichier à examiner.")
                    document = lire_paquet(fichier.read(MAX_ARCHIVE + 1))
                importer_source(document, verifier_seulement=True, ecole=None if global_ else ecole)
                contexte.update(apercu_document(document, None if global_ else ecole))
                attendu = {**engagement, "preparation": get_random_string(32), "global": global_}
                request.session[SEL] = {"jeton": attendu, "document": document}
                contexte["jeton"] = signing.dumps(attendu, salt=SEL)
            else:
                raise ValidationError("Action inconnue.")
    except ValidationError as erreur:
        contexte["erreur"] = " ".join(erreur.messages)
    except IntegrityError:
        contexte["erreur"] = "Le catalogue a changé pendant l’import. Consultez de nouveau l’aperçu."
    contexte["versions"] = versions.values()
    contexte["erreur_import"] = action in ("apercu", "apercu-grist", "importer") and "erreur" in contexte
    contexte["message_import"] = action == "importer" and "message" in contexte
    maj_import = action in ("apercu", "apercu-grist", "importer") and request.headers.get("HX-Request") == "true"
    return render(request, "suivi/paquets_referentiels.html", contexte, status=400 if "erreur" in contexte and not maj_import else 200)
