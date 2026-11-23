"""Diffusion des éditions publiques accessibles dans le contexte courant."""
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, IMPORTER_REFERENTIEL_ECOLE, VOIR_SUIVI,
                            autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .identites_referentiels import competences_document, identifiant_source_ecole
from .models import BrouillonReferentiel, ChoixApplicationAnnuel, Classe, Ecole, VersionReferentiel, annee_scolaire_pour
from .presentation import catalogue_icones
from .referentiels import adoption_courante
from .services.apercu_mises_a_jour import comparer_documents, definitions_document
from .services.choix_bases_referentiels import choix_bases, publier_choix_application
from .services.composition_referentiels import catalogue_composition, composer_paquet
from .services.import_sources_referentiels import importer_source, lire_source
from .services.paquets_referentiels import MAX_ARCHIVE, exporter_paquet, exporter_selection, lire_paquet
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
    try:
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
            elif action == "apercu":
                global_ = request.POST.get("destination") == "application"
                if (global_ and not request.user.is_superuser) or (not global_ and not peut_importer_ecole):
                    raise PermissionDenied
                fichier = request.FILES.get("paquet")
                if not fichier:
                    raise ValidationError("Choisissez le fichier à examiner.")
                document = lire_paquet(fichier.read(MAX_ARCHIVE + 1))
                importer_source(document, verifier_seulement=True, ecole=None if global_ else ecole)
                contenu, _ = lire_source(document)
                contexte["apercu"] = contenu
                identifiant = contenu["source"]["identifiant"]
                if not global_:
                    identifiant = identifiant_source_ecole(ecole, identifiant)
                precedente = VersionReferentiel.objects.filter(
                    source__identifiant=identifiant, source__ecole=None if global_ else ecole
                ).exclude(numero=contenu["version"]).order_by("-pk").first()
                if precedente:
                    contexte["comparaison_import"] = comparer_documents(precedente.contenu, contenu)
                    contexte["edition_comparee"] = precedente.numero
                contexte["destination_import"] = "de l’application" if global_ else "de l’école"
                competences = list(competences_document(contenu))
                contexte["competences_importees"] = competences
                icones = catalogue_icones()
                contexte["icones_importees"] = [icones[cle] for cle in sorted({c["icone"] for c in competences if c["icone"]})]
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
    contexte["erreur_import"] = action in ("apercu", "importer") and "erreur" in contexte
    contexte["message_import"] = action == "importer" and "message" in contexte
    maj_import = action in ("apercu", "importer") and request.headers.get("HX-Request") == "true"
    return render(request, "suivi/paquets_referentiels.html", contexte, status=400 if "erreur" in contexte and not maj_import else 200)
