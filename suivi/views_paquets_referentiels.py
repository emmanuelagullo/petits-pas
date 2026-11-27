import re
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
from .identites_referentiels import competences_document, identifiant_diffusion, identifiant_source_ecole, reference_competence
from .models import AdoptionReferentiel, BrouillonReferentiel, ChoixApplicationAnnuel, Classe, Ecole, InformationsPartageReferentielClasse, VersionReferentiel, annee_scolaire_pour
from .navigation import lien, retour_competences
from .presentation import catalogue_icones
from .referentiels import adoption_courante
from .publication_grist import ACTIONS_GRIST, historique_grist, presenter_publication_grist, publication_grist
from .services.apercu_mises_a_jour import comparer_documents, definitions_document
from .services.choix_bases_referentiels import choix_bases, publier_choix_application
from .services.composition_referentiels import catalogue_composition, composer_paquet
from .services.catalogues_externes import catalogues_grist_connus, edition_grist, identite_grist, lire_catalogue_grist, suggestions_catalogues_grist
from .services.identites_grist import classe_grist_locale
from .services.import_sources_referentiels import importer_source, lire_source
from .services.paquets_referentiels import MAX_ARCHIVE, empaqueter, exporter_paquet, exporter_selection, lire_paquet
from .services.partage_referentiel_classe import licences_referentiel_partage, preparer_referentiel_classe
from .views import acces_requis
from .noms_archives import nom_zip

SEL = "diffusion-referentiel"
SEL_PUBLICATION = "publication-referentiel"


def telecharger_paquet(donnees, titre=None, *, edition=None, type_archive="referentiel", date=None,
                       nombre_competences=None):
    compteurs = []
    if nombre_competences is not None:
        from io import BytesIO
        from zipfile import ZipFile

        with ZipFile(BytesIO(donnees)) as archive:
            icones = sum(nom.startswith("icones/") for nom in archive.namelist())
        if nombre_competences:
            compteurs.append(f"{nombre_competences}-competence{'s' if nombre_competences > 1 else ''}")
        if icones:
            compteurs.append(f"{icones}-icone{'s' if icones > 1 else ''}")
    reponse = HttpResponse(donnees, content_type="application/zip")
    nom = nom_zip(type_archive, titre, *compteurs, edition=edition, date=date)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
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
                "domaine_affiche_id": (f'{version.pk}:{competence["domaine_affiche_id"]}'
                                       if avec_source else competence["domaine_affiche_id"]),
                "edition": f"{version.source.titre} — {version.numero}" if avec_source else "",
            })
    return lignes


def apercu_document(document, ecole, *, masquer_png=False, classe=None):
    contenu, _ = lire_source(document)
    identifiant = contenu["source"]["identifiant"]
    if classe:
        from .identites_referentiels import identifiant_source_classe
        identifiant = identifiant_source_classe(classe, identifiant)
    elif ecole is not None:
        identifiant = identifiant_source_ecole(ecole, identifiant)
    precedente = VersionReferentiel.objects.filter(source__identifiant=identifiant, source__ecole=ecole
        ).exclude(numero=contenu["version"]).order_by("-pk").first()
    competences = list(definitions_document(contenu).values())
    icones = catalogue_icones()
    comparaison = comparer_documents(precedente.contenu, contenu) if precedente else None
    if masquer_png:
        for competence in competences:
            competence.pop("icone_png", None)
        if comparaison:
            lignes = []
            for titre, details in comparaison["modifications"]:
                visibles = [detail for detail in details if "png_avant" not in detail]
                if visibles:
                    lignes.append((titre, visibles))
            comparaison["modifications"] = lignes
    return {
        "apercu": contenu,
        "comparaison_import": comparaison,
        "edition_comparee": precedente.numero if precedente else None,
        "destination_import": "de l’école" if ecole else "de l’application",
        "competences_importees": competences,
        "icones_importees": [icones[cle] for cle in sorted({c["icone"] for c in competences if c["icone"]})],
    }


ACTIONS_DIRECTES_PARTAGE = {"apercu-classe", "telecharger-classe", "telecharger-icones-classe", "enregistrer-partage"} | ACTIONS_GRIST
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


def presenter_contenu_partage(classe, contexte, donnees, *, inclure_icones=False, inclure_icones_fournies=False, avec_zip=True):
    from .icones_partagees import empreinte_png, decoder_icone, png_en_ligne

    source = {k: donnees[k] for k in ("identifiant", "titre", "provenance", "licence")}
    source["licence_creations"] = donnees.get("licence_creations", "")
    document = preparer_referentiel_classe(classe, source, donnees["version"])
    from .services.licences_diffusion import LICENCE_PROPOSEE, droits_competence
    from .services.partage_referentiel_classe import (
        compter_creations_sans_licence, licence_creations_classe, verifier_licence_synchronisation,
    )

    try:
        document["source"]["licence"] = verifier_licence_synchronisation(adoption_courante(classe), document)
    except ValidationError:
        # L'aperçu permet de choisir une licence ou de télécharger les compétences prêtes.
        pass
    reglage_creations = licence_creations_classe(adoption_courante(classe))
    contexte["proposition_creations_partage"] = compter_creations_sans_licence(classe, document) if not reglage_creations else 0
    contexte["licence_proposee_creations_partage"] = source["licence_creations"] or reglage_creations or LICENCE_PROPOSEE
    droits = [(c["libelle"], droits_competence(document, c)[0]) for c in competences_document(document)]
    contexte["revisions_licence"] = [libelle for libelle, licence in droits if not licence]
    contexte["references_licence"] = [reference_competence(c) for c in competences_document(document)
                                     if not droits_competence(document, c)[0]]
    contexte["licences_partage"] = sorted({licence for _, licence in droits if licence})
    contexte["nombre_licences_partage"] = len(contexte["licences_partage"])
    contexte["nombre_exportable_partage"] = sum(bool(licence) for _, licence in droits)
    contexte["empreinte_licences_partage"] = sha256(yaml.safe_dump(droits, allow_unicode=True).encode()).hexdigest()
    empreintes = set()
    for competence in competences_document(document):
        png = competence.get("icone_png")
        if png:
            octets = png_en_ligne(png)
            empreintes.add(empreinte_png(decoder_icone(octets)))
            if inclure_icones:
                competence["icone_png"] = octets
            else:
                competence.pop("icone_png", None)
    nombre = len(empreintes)
    contexte["nombre_icones_ajoutees"] = nombre
    # Une licence manquante n'empêche pas de consulter la projection.
    a_lire = {**document, "source": {**document["source"], "licence": document["source"]["licence"] or "À vérifier"}}
    paquet = empaqueter(a_lire, inclure_icones_fournies=inclure_icones_fournies) if avec_zip else None
    normalise, _ = lire_source(yaml.safe_dump(a_lire, allow_unicode=True))
    icones = catalogue_icones()
    contexte["apercu_partage"] = {
        "apercu": normalise, "competences_importees": list(definitions_document(normalise).values()),
        "icones_importees": [icones[cle] for cle in sorted({
            c["icone"] for c in competences_document(normalise) if c["icone"]
        })],
    }
    return document, paquet, normalise


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
    partiel = action == "telecharger-classe" and request.POST.get("competences_pretes") == "oui"
    direct = action in ACTIONS_DIRECTES_PARTAGE
    from .services.licences_diffusion import LICENCE_PROPOSEE

    formulaire = PartageReferentielClasseForm(
        request.POST if direct and "titre" in request.POST else None,
        initial={**initial, "licence": initial["licence"] or LICENCE_PROPOSEE},
    )
    contexte["partage_classe"] = formulaire
    if action in ACTIONS_GRIST:
        contexte["destination_export"] = "grist"
    elif action in {"telecharger-classe", "telecharger-icones-classe", "exporter-classe"}:
        contexte["destination_export"] = "zip"
    presenter_publication_grist(request, classe, contexte, initial["identifiant"])
    if action not in ACTIONS_PARTAGE:
        if contexte.get("volet") in ("exporter", "", None):
            presenter_contenu_partage(classe, contexte, initial, avec_zip=False)
        return
    contexte["volet"] = "exporter"
    engagement = {"auteur": request.user.pk, "adoption": adoption.pk}
    if direct:
        if formulaire.is_bound and not formulaire.is_valid():
            contexte["modifier_partage"] = True
            return
        donnees = formulaire.cleaned_data if formulaire.is_bound else initial
        if partiel and not donnees["licence"]:
            donnees = {**donnees, "licence": "À vérifier"}
        formulaire = PartageReferentielClasseForm(donnees)
        contexte["partage_classe"] = formulaire
        if not formulaire.is_valid() or (base_changee and not partiel and "titre" not in request.POST):
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
    inclure_icones = (
        action in {"voir-grist", "publier-grist", "telecharger-icones-classe"}
        or (request.POST.get("inclure_icones") == "oui" if direct else preparation.get("inclure_icones", False))
    )
    contexte["inclure_icones"] = inclure_icones
    inclure_icones_fournies = (request.POST.get("inclure_icones_fournies") == "oui" if direct else
                               preparation.get("inclure_icones_fournies", False))
    if action in ACTIONS_GRIST:
        inclure_icones_fournies = False
    contexte["inclure_icones_fournies"] = inclure_icones_fournies
    document, paquet, normalise = presenter_contenu_partage(
        classe, contexte, donnees, inclure_icones=inclure_icones,
        inclure_icones_fournies=inclure_icones_fournies,
        avec_zip=action in {"telecharger-classe", "exporter-classe"},
    )
    empreinte = sha256(yaml.safe_dump(document, allow_unicode=True).encode()).hexdigest()
    if not direct and empreinte != preparation["empreinte"]:
        raise ValidationError("Le référentiel a changé. Examinez de nouveau le contenu à partager.")
    licences = licences_referentiel_partage(adoption, document)
    if action == "enregistrer-partage" and contexte["revisions_licence"] and request.POST.get("autorisation_partage") != "oui":
        contexte["modifier_partage"] = True
        raise ValidationError("Confirmez l’autorisation de partager les compétences sans licence renseignée.")
    if action in {"telecharger-classe", "exporter-classe", "publier-grist"}:
        from .services.partage_referentiel_classe import verifier_licence_synchronisation

        if partiel:
            if contexte["empreinte_licences_partage"] != request.POST.get("empreinte_licences"):
                raise ValidationError("Le périmètre de l’export a changé. Vérifiez les compétences prêtes.")
            from .services.licences_diffusion import retirer_droits_inconnus

            if not retirer_droits_inconnus(document):
                raise ValidationError("Renseignez les licences avant de télécharger.")
            contenu = yaml.safe_dump(document, allow_unicode=True)
            document["source"].update(
                identifiant="selection-" + sha256(contenu.encode()).hexdigest(),
                titre=f"Sélection · {donnees['titre']}"[:200],
            )
        else:
            document["source"]["licence"] = verifier_licence_synchronisation(adoption, document)
        # Le document normalisé utilisé par Grist et le ZIP doivent conserver les mêmes droits.
        normalise, _ = lire_source(yaml.safe_dump(document, allow_unicode=True))
        if action in {"telecharger-classe", "exporter-classe"}:
            paquet = empaqueter(document, inclure_icones_fournies=inclure_icones_fournies)
    contexte["modifier_partage"] = False
    sauvegardees = informations_partage(classe, adoption)[0].get("competences_licence_confirmee", [])
    portee = contexte["references_licence"] if action == "enregistrer-partage" and contexte["references_licence"] else sauvegardees
    licence_creations = donnees.get("licence_creations") or initial.get("licence_creations", "")
    if contexte["proposition_creations_partage"] and action in {"telecharger-classe", "exporter-classe", "publier-grist"}:
        licence_creations = contexte["licence_proposee_creations_partage"]
    enregistrement = {"donnees": {**donnees, "competences_licence_confirmee": portee,
                                 "licence_creations": licence_creations},
                      "adoption": adoption, "licences_sources": licences}
    if action == "telecharger-icones-classe":
        from .icones_partagees import externaliser_png
        from .services.paquets_referentiels import empaqueter_icones

        return telecharger_paquet(empaqueter_icones(externaliser_png(normalise)), donnees["titre"],
                                  type_archive="icones", nombre_competences=0)
    if partiel:
        return telecharger_paquet(paquet, document["source"]["titre"], edition=donnees["version"],
                                  type_archive="referentiel-selection", date=timezone.now(),
                                  nombre_competences=sum(1 for _ in competences_document(document)))
    if action in ("telecharger-classe", "exporter-classe"):
        InformationsPartageReferentielClasse.objects.update_or_create(
            classe=classe, defaults=enregistrement,
        )
        return telecharger_paquet(paquet, donnees["titre"], edition=donnees["version"], date=timezone.now(),
                                  nombre_competences=len(contexte["apercu_partage"]["competences_importees"]))
    if action == "enregistrer-partage":
        InformationsPartageReferentielClasse.objects.update_or_create(classe=classe, defaults=enregistrement)
        presenter_contenu_partage(classe, contexte, donnees, avec_zip=False)
        presenter_publication_grist(request, classe, contexte, donnees["identifiant"])
        return
    if action in ACTIONS_GRIST:
        try:
            publication_grist(request, classe, contexte, action, normalise)
        except ValidationError as erreur:
            contexte["erreur_grist"] = " ".join(erreur.messages)
        if contexte.get("publication_grist_reussie"):
            InformationsPartageReferentielClasse.objects.update_or_create(classe=classe, defaults=enregistrement)
            presenter_publication_grist(request, classe, contexte, donnees["identifiant"])
        return
    if direct:
        contexte["jeton_partage"] = signing.dumps(
            {"engagement": engagement, "donnees": donnees, "empreinte": empreinte, "inclure_icones": inclure_icones,
             "inclure_icones_fournies": inclure_icones_fournies},
            salt="partage-referentiel-classe",
        )
    else:
        contexte["jeton_partage"] = request.POST["jeton_partage"]



def presenter_import_grist(request, ecole, contexte):
    from .services.catalogues_externes import reglages_catalogues_classe

    classe = contexte.get("classe")
    reglages = reglages_catalogues_classe(classe) if contexte.get("import_classe") else ecole.catalogues_referentiels
    catalogues = catalogues_grist_connus(reglages)
    suggestions = {suggestion["url"]: suggestion for suggestion in suggestions_catalogues_grist(
        request.user, ecole, classe, prioritaires=catalogues.values(),
    )}
    choix = request.GET.get("catalogue_import")
    choisi = suggestions.get(choix)
    if choisi and choix not in catalogues and request.method == "GET":
        try:
            catalogues[choix] = lire_catalogue_grist(choix)
        except ValidationError as erreur:
            contexte["erreur_catalogue_import"] = " ".join(erreur.messages)
    base = contexte.get("base_du_partage")
    source = identifiant_diffusion(base.source) if base else None
    lignes = []
    for url, catalogue in catalogues.items():
        suivis = reglages.get(url, {}).get("suivis", ())
        for referentiel in catalogue["referentiels"]:
            reference = referentiel["reference"]
            courant = source is not None and identite_grist(catalogue["url"], reference) == source
            if choisi is not None and choix != url:
                continue
            if choisi is None and reference not in suivis and not courant:
                continue
            lignes.append({**referentiel, "url": catalogue["url"], "catalogue": catalogue["nom"],
                           "derniere": referentiel["editions"][0], "courant": courant})
    contexte.update(catalogues_import=suggestions.values(), catalogue_import=choisi,
                    editions_import=sorted(lignes, key=lambda ligne: not ligne["courant"]))


def partage_selection_classe(request, classe, contexte):
    from .services.selection_partagee import preparer_selection
    from .services.partage_referentiel_classe import licence_creations_classe
    from .services.licences_diffusion import LICENCE_PROPOSEE, LICENCES_RECONNUES

    adoption = adoption_courante(classe)
    if classe.etat != Classe.ACTIVE or not adoption or adoption.clos:
        raise PermissionDenied
    references = request.POST.getlist("competence_partagee")
    choix = request.POST.getlist("definition") + [
        valeur for nom, valeur in request.POST.items() if nom.startswith("definition_")
    ]
    contexte.update(
        export_selection=True, volet="exporter", peut_importer=False,
        retour_competences=retour_competences(request, classe) or lien("catalogue_competences", classe.pk),
        references_selection=references, definitions_selection=choix,
    )
    try:
        action_selection = request.POST.get("action")
        licence = request.POST.get("licence_confirmee", "")
        if action_selection == "confirmer-licence-selection" and request.POST.get("autorisation") != "oui":
            raise ValidationError("Confirmez l’autorisation de partager sous la licence choisie.")
        if request.POST.get("autorisation") != "oui":
            licence = ""
        if licence and licence not in LICENCES_RECONNUES:
            raise ValidationError("Confirmez l’autorisation de partager sous la licence choisie.")
        licence_creation = request.POST.get("licence_creation") or licence_creations_classe(adoption) or LICENCE_PROPOSEE
        if licence_creation not in LICENCES_RECONNUES:
            raise ValidationError("Choisissez une licence proposée pour vos créations.")
        document, sources, credits, conflits, manquantes, nombre_licences, creations = preparer_selection(
            request.user, adoption, references, choix, licence_confirmee=licence,
            licence_creation=licence_creation,
        )
        nombre_exportable = sum(1 for _ in competences_document(document))
        from .icones_partagees import png_en_ligne

        for competence in competences_document(document):
            if competence.get("icone_png"):
                competence["icone_png"] = png_en_ligne(competence["icone_png"])
        icones = {c["icone_png"] for c in competences_document(document) if c.get("icone_png")}
        empreinte = sha256(yaml.safe_dump(document, allow_unicode=True).encode()).hexdigest()
        titre = request.POST.get("titre_selection", "").strip() or document["source"]["titre"]
        if len(titre) > 200:
            raise ValidationError("Le titre est limité à 200 caractères.")
        document["source"]["titre"] = titre
        contexte.update(
            nombre_icones_ajoutees=len(icones),
            apercu_selection=apercu_document(yaml.safe_dump(document, allow_unicode=True), classe.ecole, classe=classe)
                if nombre_exportable else None,
            selection_calculee=True, nombre_exportable=nombre_exportable,
            licences_manquantes=manquantes, nombre_licences=nombre_licences,
            licence_proposee=LICENCE_PROPOSEE, choix_licences=sorted(LICENCES_RECONNUES),
            licence_confirmee=licence, licence_creation=licence_creation, nombre_creations=len(creations),
            titre_selection=titre, sources_selection=sources, credits_selection=credits,
            conflits_selection=conflits,
            empreinte_selection=empreinte, inclure_icones_selection=request.POST.get("inclure_icones") == "oui",
        )
        if request.POST.get("action") == "telecharger-selection-classe":
            if conflits or not nombre_exportable:
                raise ValidationError("Vérifiez les définitions et les licences avant le téléchargement.")
            if empreinte != request.POST.get("empreinte"):
                raise ValidationError("Le contenu a changé. Vérifiez la sélection avant de télécharger.")
            if not contexte["inclure_icones_selection"]:
                for competence in competences_document(document):
                    competence.pop("icone_png", None)
            reponse = telecharger_paquet(empaqueter(document, inclure_icones_fournies=False), titre,
                                         type_archive="referentiel-selection", edition="1", date=timezone.now(),
                                         nombre_competences=nombre_exportable)
            from .models import CompetenceLocale

            CompetenceLocale.objects.filter(pk__in=creations, auteur=request.user, licence_partage="").update(
                licence_partage=licence_creation,
            )
            return reponse
    except ValidationError as erreur:
        contexte["erreur_selection"] = " ".join(erreur.messages)
    contexte["titre_echange"] = "Exporter la sélection"
    contexte["afficher_export"] = True
    return render(request, "suivi/paquets_referentiels.html", contexte,
                  status=400 if "erreur_selection" in contexte else 200)


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
    import_classe = bool(classe and request.GET.get("destination") == "classe")
    if import_classe and classe.etat != Classe.ACTIVE:
        raise PermissionDenied
    peut_importer_ecole = autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, classe or ecole)
    peut_gerer_ecole = autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole)
    contexte = {"retour_catalogues": "", "retour_competences": "", "retour_decouverte": "", "classe": classe, "annee": annee, "volet": request.GET.get("volet"), "peut_importer": import_classe or peut_importer_ecole or request.user.is_superuser, "import_classe": import_classe,
                "peut_importer_ecole": peut_importer_ecole, "peut_importer_global": request.user.is_superuser and not import_classe}
    if action in ("preparer-selection-classe", "confirmer-licence-selection", "telecharger-selection-classe"):
        if classe is None:
            raise PermissionDenied
        return partage_selection_classe(request, classe, contexte)
    if classe and request.GET.get("depuis") == "catalogues":
        groupe = request.GET.get("catalogue", "")
        contexte["retour_catalogues"] = lien("suivis_referentiels_classe", classe.pk,
                                             catalogue=groupe, ancre=groupe)
    if classe and request.GET.get("depuis") == "competences":
        contexte["retour_competences"] = retour_competences(request, classe) or lien(
            "catalogue_competences", classe.pk, ancre="actions-referentiel-classe" if import_classe else "partager-competences",
        )
    if classe and request.GET.get("depuis") == "reglages":
        contexte["retour_reglages"] = lien("referentiel_classe", classe.pk, ancre="importer-partager")
    if classe and request.GET.get("depuis") == "espace":
        contexte["retour_espace"] = lien("suivis_referentiels_classe", classe.pk, espace=1, ancre="espace-partage")
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
        if peut_importer_ecole or import_classe:
            presenter_import_grist(request, ecole, contexte)
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
                    catalogue, brouillon, brouillon["reprises"], brouillon["creations"]),
                    brouillon["titre"], edition=brouillon["version"], date=timezone.now())
            if action in ("enregistrer_composition", "ajouter_ligne_composition"):
                contexte["message"] = "Brouillon enregistré pour cette année."
                action = None
        engagement = {"auteur": request.user.pk, "ecole": ecole.pk, "classe": classe_pk, "annee": annee, "import_classe": import_classe}
        if request.method == "GET" and import_classe and request.GET.get("reprendre") == "1":
            preparation = request.session.get(SEL, {})
            attendu = preparation.get("jeton", {})
            try:
                jeton = preparation.get("reprise", "")
                if jeton and signing.loads(jeton, salt=SEL, max_age=1800) == attendu and all(
                    attendu.get(cle) == valeur for cle, valeur in engagement.items()
                ):
                    contexte.update(apercu_document(preparation["document"], ecole, classe=classe),
                                    jeton=jeton, destination_import="de la classe")
            except signing.BadSignature:
                pass
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
                return telecharger_paquet(donnees, version.source.titre,
                    edition=version.numero if action == "edition" else None,
                    type_archive="referentiel" if action == "edition" else "referentiel-selection")
            if not contexte["peut_importer"]:
                raise PermissionDenied
            if action in ("telecharger-icones-grist", "importer-icones-zip", "importer-icones-grist"):
                if import_classe:
                    raise PermissionDenied
                from .models import IconePartagee, IconeRecueEcole
                from .services.catalogues_externes import icones_catalogue_grist
                from .services.paquets_referentiels import empaqueter_icones, lire_paquet_icones

                if not peut_importer_ecole:
                    raise PermissionDenied
                if action != "importer-icones-zip":
                    url = request.POST.get("catalogue", "")
                    ressources = icones_catalogue_grist(url)
                    if action == "telecharger-icones-grist":
                        return telecharger_paquet(empaqueter_icones(ressources), type_archive="icones",
                                                  nombre_competences=0)
                    if not ressources:
                        raise ValidationError("Ce catalogue ne contient aucune icône ajoutée.")
                else:
                    fichier = request.FILES.get("icones_zip")
                    if not fichier:
                        raise ValidationError("Choisissez un ZIP d’icônes.")
                    ressources = lire_paquet_icones(fichier.read(MAX_ARCHIVE + 1))
                with transaction.atomic():
                    for cle, png in ressources.items():
                        icone, _ = IconePartagee.objects.get_or_create(empreinte=cle, defaults={"png": png})
                        IconeRecueEcole.objects.get_or_create(ecole=ecole, icone=icone)
                contexte["message"] = f"Icônes vérifiées et enregistrées : {len(ressources)}."
            elif action == "ouvrir-catalogue-grist":
                if not (peut_importer_ecole or import_classe):
                    raise PermissionDenied
                contexte["lien_catalogue_import"] = request.POST.get("lien_catalogue_import", "")[:2000]
                catalogue = lire_catalogue_grist(contexte["lien_catalogue_import"])
                contexte["catalogue_import"] = catalogue
                contexte["editions_import"] = [
                    {**ligne, "catalogue": catalogue["nom"], "url": catalogue["url"],
                     "derniere": ligne["editions"][0]} for ligne in catalogue["referentiels"]
                ]
            elif action == "importer":
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
                        droit = GERER_REFERENTIEL_CLASSE if import_classe else IMPORTER_REFERENTIEL_ECOLE
                        if (import_classe and classe.etat != Classe.ACTIVE) or not autorise(request.user, droit, classe or ecole):
                            raise PermissionDenied
                    if classe_grist_locale(ecole, attendu.get("reference_courante")):
                        raise ValidationError("Ce référentiel est déjà disponible dans ce Petits Pas.")
                    edition_importee, cree, _ = importer_source(
                        preparation["document"], ecole=None if attendu["global"] else ecole,
                        classe=classe if import_classe else None)
                if import_classe:
                    adoption = adoption_courante(classe)
                    if adoption and not adoption.clos:
                        contexte["lien_reprise"] = lien(
                            "catalogue_competences", classe.pk, source=f"version-{edition_importee.pk}",
                        )
                elif not attendu["global"]:
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
                cible = "de la classe" if import_classe else "de l’application" if attendu["global"] else "de l’école"
                contexte["message"] = (f"Édition ajoutée au catalogue {cible}." if cree else
                                       f"Cette édition figure déjà dans le catalogue {cible}.")
            elif action in ("apercu", "apercu-grist"):
                global_ = not import_classe and action == "apercu" and request.POST.get("destination") == "application"
                if (global_ and not request.user.is_superuser) or (not global_ and not (peut_importer_ecole or import_classe)):
                    raise PermissionDenied
                masquer_png = False
                reference_courante = None
                if action == "apercu-grist":
                    numero = request.POST.get("numero", "")
                    if not re.fullmatch(r"[0-9a-f]{64}", numero):
                        try:
                            numero = int(numero)
                        except ValueError as erreur:
                            raise ValidationError("Choisissez une édition Grist à examiner.") from erreur
                    reference = request.POST.get("reference", "")
                    if classe_grist_locale(ecole, reference):
                        raise ValidationError("Ce référentiel est déjà disponible dans ce Petits Pas.")
                    if re.fullmatch(r"[0-9a-f]{64}", str(numero)):
                        reference_courante = reference
                    document, catalogue = edition_grist(
                        request.POST.get("catalogue", ""), request.POST.get("reference"), numero, avec_catalogue=True,
                    )
                    masquer_png = catalogue["mode_contenu"] == "competences"
                else:
                    fichier = request.FILES.get("paquet")
                    if not fichier:
                        raise ValidationError("Choisissez le fichier à examiner.")
                    document = lire_paquet(fichier.read(MAX_ARCHIVE + 1))
                importer_source(document, verifier_seulement=True, ecole=None if global_ else ecole,
                                classe=classe if import_classe else None)
                contexte.update(apercu_document(document, None if global_ else ecole, masquer_png=masquer_png, classe=classe if import_classe else None))
                if import_classe:
                    contexte["destination_import"] = "de la classe"
                attendu = {**engagement, "preparation": get_random_string(32), "global": global_,
                           "reference_courante": reference_courante}
                contexte["jeton"] = signing.dumps(attendu, salt=SEL)
                request.session[SEL] = {"jeton": attendu, "document": document, "reprise": contexte["jeton"]}
            else:
                raise ValidationError("Action inconnue.")
    except ValidationError as erreur:
        contexte["erreur"] = " ".join(erreur.messages)
    except IntegrityError:
        contexte["erreur"] = "Le catalogue a changé pendant l’import. Consultez de nouveau l’aperçu."
    if (classe and contexte.get("retour_espace") and request.GET.get("licence") == "1"
            and request.headers.get("HX-Request") == "true"):
        contexte["modifier_partage"] = True
        contexte["licence_enregistree"] = request.POST.get("action") == "enregistrer-partage" and not (
            contexte.get("erreur") or getattr(contexte.get("partage_classe"), "errors", None)
            or contexte.get("revisions_licence")
        )
        return render(request, "suivi/partiels/licence_partage_sur_place.html", contexte)
    volet = contexte.get("volet")
    import_explicite = volet == "importer" or import_classe or (
        action in {"apercu", "apercu-grist", "importer", "ouvrir-catalogue-grist", "importer-icones-zip", "importer-icones-grist", "telecharger-icones-grist"}
    )
    contexte["afficher_import"] = contexte["peut_importer"] and (import_explicite or not volet)
    contexte["afficher_export"] = not import_explicite
    if import_explicite:
        contexte["titre_echange"] = (
            "Examiner une édition" if contexte["retour_catalogues"] else
            "Importer un ZIP pour la classe" if import_classe else "Importer un référentiel"
        )
    else:
        contexte["titre_echange"] = "Partager le référentiel de la classe" if classe else "Exporter une édition"
    contexte["versions"] = versions.values()
    contexte["erreur_import"] = action in ("apercu", "apercu-grist", "importer", "ouvrir-catalogue-grist", "telecharger-icones-grist", "importer-icones-zip", "importer-icones-grist") and "erreur" in contexte
    contexte["message_import"] = action in ("importer", "importer-icones-zip", "importer-icones-grist") and "message" in contexte
    maj_import = action in ("apercu", "apercu-grist", "importer") and request.headers.get("HX-Request") == "true"
    if (maj_import and import_classe and contexte["retour_catalogues"]
            and request.POST.get("fragment_catalogue") == "1"):
        return render(request, "suivi/partiels/reponse_examen_catalogue.html", contexte)
    return render(request, "suivi/paquets_referentiels.html", contexte, status=400 if "erreur" in contexte and not maj_import else 200)
