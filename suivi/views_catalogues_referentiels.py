"""Découverte et suivi des référentiels à l’échelle d’une école."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .autorisations import (GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, IMPORTER_REFERENTIEL_ECOLE,
                            autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .identites_referentiels import identifiant_source_ecole
from .models import ChoixApplicationAnnuel, DestinationPublicationGrist, Ecole, VersionReferentiel, annee_scolaire_pour
from .navigation import lien
from .services.catalogue_fourni import REFERENTIELS_DEPART
from .services.catalogues_externes import adresse_grist, catalogues_grist_connus, enregistrer_nom_catalogue_grist, identite_grist, lire_catalogue_grist, partage_grist_disponible
from .services.choix_bases_referentiels import choix_bases, verifier_annee
from .views import acces_requis

@lru_cache(maxsize=1)
def referentiels_fournis():
    resultat = []
    for cle, titre, chemin in REFERENTIELS_DEPART:
        document = yaml.safe_load((Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8"))
        source = document["source"]
        resultat.append({"reference": cle, "identifiant_local": source["identifiant"], "titre": titre,
                         "editions": [document["version"]], "provenance": source["provenance"],
                         "licence": source["licence"]})
    return resultat


def catalogue_instance(annee):
    referentiels = {source["identifiant_local"]: {**source, "fourni": True}
                   for source in referentiels_fournis()}
    choix = ChoixApplicationAnnuel.objects.filter(annee_scolaire=annee, configure=True).first()
    if choix:
        versions = choix.versions_autorisees.filter(source__ecole__isnull=True,
            contenu__origine="source_declaree").select_related("source").order_by("-pk")
        for version in versions:
            source = version.source
            ligne = referentiels.setdefault(source.identifiant, {
                "reference": source.identifiant, "identifiant_local": source.identifiant,
                "titre": source.titre, "provenance": source.provenance, "licence": source.licence,
            })
            ligne.setdefault("versions_instance", []).append(version)
        for ligne in referentiels.values():
            if "versions_instance" in ligne:
                ligne["editions"] = [version.numero for version in ligne["versions_instance"]]
    return {"nom": "Catalogue de cette instance Petits Pas", "referentiels": list(referentiels.values())}


def catalogues_visibles(reglages, instance):
    return {
        "petits-pas": instance,
        **catalogues_grist_connus(reglages),
    }


def catalogue_suivi(etat):
    return etat.get("suivre_catalogue", bool(etat.get("suivis")))


def enregistrer_catalogue(ecole, utilisateur, cle, *, catalogue=None, reference=None, suivre=False, suivre_catalogue=None):
    with transaction.atomic():
        ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
        if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
            raise PermissionDenied
        etat = ecole.catalogues_referentiels.setdefault(cle, {})
        if catalogue is not None:
            etat["catalogue"] = catalogue
        if suivre_catalogue is not None:
            etat["suivre_catalogue"] = suivre_catalogue
        if reference is not None:
            suivis = set(etat.get("suivis", ()))
            if suivre:
                suivis.add(reference)
            else:
                suivis.discard(reference)
            etat["suivis"] = sorted(suivis)
            if suivre and "suivre_catalogue" not in etat:
                etat["suivre_catalogue"] = True
        ecole.save(update_fields=["catalogues_referentiels"])
    return ecole


@acces_requis
@require_http_methods(["GET", "POST"])
def decouvrir_referentiels(request):
    ecole = ecole_courante(request)
    peut_gerer = autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole)
    annee = request.GET.get("annee") or annee_scolaire_pour(timezone.localdate())
    try:
        verifier_annee(annee)
    except ValidationError as erreur:
        raise Http404 from erreur
    q = request.GET.get("q", "").strip()[:200]
    filtre = request.GET.get("filtre", "")
    if filtre not in {"suivis", "mises-a-jour"}:
        filtre = ""
    navigation = {"depuis": "echange"} if request.GET.get("depuis") == "echange" else {}
    retour_classe = request.GET.get("classe", "")
    if retour_classe.isdecimal() and len(retour_classe) < 18:
        classe = charger_classe_autorisee(request.user, int(retour_classe), GERER_REFERENTIEL_CLASSE, ecole=ecole)
        navigation["classe"] = classe.pk
    else:
        classe = None
    if not peut_gerer and (classe is None or request.method == "POST"):
        raise PermissionDenied
    retour = lien("decouvrir_referentiels", annee=annee, q=q, filtre=filtre, **navigation)
    contexte = {"annee": annee, "q": q, "filtre": filtre, "retour": retour,
                "depuis_echange": navigation.get("depuis") == "echange",
                "classe_origine": classe, "peut_gerer": peut_gerer,
                "depuis_classe": bool(classe),
                "examen_grist": lien("paquets_referentiels_ecole", annee=annee, origine="decouverte",
                                     q=q, filtre=filtre, **navigation),
                "peut_importer": autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, ecole)}
    invitation = request.GET.get("catalogue_invite", "")
    if invitation and peut_gerer:
        try:
            adresse_grist(invitation)
        except ValidationError as cause:
            contexte["erreur"] = " ".join(cause.messages)
        else:
            contexte["url_saisie"] = invitation
            contexte["invitation_catalogue"] = True
    instance = catalogue_instance(annee)
    catalogues = catalogues_visibles(ecole.catalogues_referentiels, instance)
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "ajouter":
                contexte["url_saisie"] = request.POST.get("url", "")[:2000]
                catalogue = lire_catalogue_grist(contexte["url_saisie"])
                ecole = enregistrer_catalogue(ecole, request.user, catalogue["url"], catalogue=catalogue)
                contexte.update(catalogue_ajoute=catalogue, message="Catalogue disponible. Choisissez les référentiels à suivre.")
            elif action == "renommer-catalogue":
                cle = request.POST.get("catalogue")
                catalogue = catalogues.get(cle)
                if not catalogue or not catalogue.get("url"):
                    raise ValidationError("Choisissez un catalogue Grist connu de l’école.")
                nom = enregistrer_nom_catalogue_grist(catalogue["url"], request.POST.get("nom_catalogue", ""),
                                                       remplacer=True)
                ecole = enregistrer_catalogue(ecole, request.user, cle, catalogue={**catalogue, "nom": nom})
                DestinationPublicationGrist.objects.filter(ecole=ecole, url=catalogue["url"]).update(nom=nom)
                contexte["message"] = "Nom enregistré dans Grist."
            elif action == "verifier":
                erreurs, nouveautes = [], set()
                for cle, catalogue in catalogues.items():
                    if catalogue.get("url") and catalogue_suivi(ecole.catalogues_referentiels.get(cle, {})):
                        try:
                            actualise = lire_catalogue_grist(catalogue["url"])
                            connues = {ligne["reference"] for ligne in catalogue["referentiels"]}
                            nouveautes.update((cle, ligne["reference"]) for ligne in actualise["referentiels"]
                                              if ligne["reference"] not in connues)
                            ecole = enregistrer_catalogue(ecole, request.user, cle, catalogue=actualise)
                        except ValidationError as erreur:
                            erreurs.append(f'{catalogue["nom"]} — {" ".join(erreur.messages)}')
                contexte.update(erreurs_verification=erreurs, nouveautes=nouveautes, message="Vérification terminée.")
            elif action in {"suivre-catalogue", "ne-plus-suivre-catalogue"}:
                cle = request.POST.get("catalogue")
                if not catalogues.get(cle, {}).get("url"):
                    raise ValidationError("Ce catalogue en ligne n’est pas disponible.")
                enregistrer_catalogue(ecole, request.user, cle, suivre_catalogue=action == "suivre-catalogue")
                return redirect(retour)
            elif action in {"suivre", "ne-plus-suivre"}:
                cle, reference = request.POST.get("catalogue"), request.POST.get("reference")
                if not any(ligne["reference"] == reference for ligne in catalogues.get(cle, {}).get("referentiels", [])):
                    raise ValidationError("Ce référentiel n’est plus proposé.")
                enregistrer_catalogue(ecole, request.user, cle, reference=reference, suivre=action == "suivre")
                return redirect(retour)
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            contexte["erreur"] = " ".join(erreur.messages)

    regles = ecole.catalogues_referentiels
    versions = {}
    for identifiant, numero in VersionReferentiel.objects.filter(
            Q(source__ecole=ecole) | Q(source__ecole__isnull=True)).values_list(
            "source__identifiant", "numero").order_by("pk"):
        versions.setdefault(identifiant, []).append(numero)
    autorisees = {version.pk for version in choix_bases(ecole, annee).versions}
    groupes = []
    contexte["a_des_suivis"] = any(catalogue.get("url") and catalogue_suivi(regles.get(cle, {}))
                                   for cle, catalogue in catalogues_visibles(regles, instance).items())
    texte_recherche = slugify(q)
    termes = texte_recherche.split("-") if texte_recherche else []
    for cle, catalogue in catalogues_visibles(regles, instance).items():
        lignes = []
        ajoute = contexte.get("catalogue_ajoute", {}).get("url") == cle
        for source in catalogue["referentiels"]:
            reference = source["reference"]
            url = catalogue.get("url")
            identifiant = identifiant_source_ecole(ecole, identite_grist(url, reference)) if url else source["identifiant_local"]
            locales = versions.get(identifiant, [])
            derniere = source["editions"][0]
            suivi = reference in regles.get(cle, {}).get("suivis", ())
            mise_a_jour = bool(url and locales) and str(derniere) not in locales
            ligne = {**source, "cle": cle, "url": url,
                     "nouveau": (cle, reference) in contexte.get("nouveautes", ()),
                     "suivi": suivi, "locales": locales, "derniere": derniere, "mise_a_jour": mise_a_jour,
                     "locale": str(derniere) in locales}
            version_consultable = next((version for version in source.get("versions_instance", ())
                                        if version.pk in autorisees), None)
            if version_consultable and peut_gerer:
                ligne["consultation"] = lien("consulter_referentiels_ecole", annee=annee,
                                             version=version_consultable.pk)
                ligne["edition_consultable"] = version_consultable.numero
            if ligne["nouveau"] or ajoute or (all(terme in slugify(f'{source["titre"]} {catalogue["nom"]}') for terme in termes)
                          and (filtre != "suivis" or suivi) and (filtre != "mises-a-jour" or mise_a_jour)):
                lignes.append(ligne)
        if ajoute or lignes or (not q and not filtre):
            groupes.append({"nom": catalogue["nom"], "url": catalogue.get("url"), "lignes": lignes,
                            "cle": cle, "suivi": catalogue_suivi(regles.get(cle, {}))})
    contexte.update(groupes=groupes, nombre_resultats=sum(len(groupe["lignes"]) for groupe in groupes))
    return render(request, "suivi/decouvrir_referentiels.html", contexte)


def empreinte_suivi(valeur):
    return hashlib.sha256(json.dumps(valeur, sort_keys=True).encode()).hexdigest()


@acces_requis
@require_http_methods(["GET", "POST"])
def suivis_classe(request, classe_pk):
    from .models import SuiviSourceClasse
    from .referentiels import adoption_courante
    from .services.sources_catalogue import lignes_source, sources_catalogue

    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    adoption = adoption_courante(classe)
    autorisees = {v.pk for v in choix_bases(ecole, classe.annee_scolaire).versions}
    retour = lien("suivis_referentiels_classe", classe.pk, ancre="referentiels-suivis")
    disponibles = {}
    if adoption and not adoption.clos:
        sources = sources_catalogue(request.user, classe, adoption)
        sources[f"version-{adoption.version_id}"] = (
            adoption.version.source.titre, adoption.version, None)
        for cle, (titre, version, autre) in sources.items():
            reference = f"source-{version.source_id}" if version else cle
            ligne = disponibles.get(reference)
            if ligne and version.pk <= ligne["version"].pk:
                continue
            disponibles[reference] = {"cle": cle, "titre": titre, "version": version, "autre": autre}

    suivis = {s.reference: s for s in SuiviSourceClasse.objects.filter(classe=classe)}
    action = request.POST.get("action")
    cible = request.POST.get("source")
    from .identites_referentiels import est_uuid_portable

    divergences = {}
    lignes = []
    for reference, ligne in disponibles.items():
        version, autre = ligne["version"], ligne["autre"]
        suivi = suivis.get(reference)
        courant = bool(version and version.source_id == adoption.version.source_id)
        etat = {}
        empreinte = ""
        if suivi or (action == "suivre" and reference == cible):
            definitions = list(lignes_source(version, autre, utilisateur=request.user, classe=classe))
            if suivi:
                for ref, competence, _, _ in definitions:
                    if est_uuid_portable(ref):
                        divergences.setdefault(ref, []).append({
                            "titre": ligne["titre"], "libelle": competence["libelle"],
                            "signature": empreinte_suivi([competence.get(c) for c in
                                ("libelle", "niveau", "icone", "icone_png", "formulations", "active")]),
                            "url": lien("catalogue_competences", classe.pk, source=ligne["cle"],
                                        q=competence["libelle"]),
                        })
            etat = {
                ref: {"libelle": c["libelle"], "empreinte": empreinte_suivi([
                    d, s, {cle: c.get(cle) for cle in ("libelle", "niveau", "icone", "icone_png", "formulations", "active")},
                ])}
                for ref, c, d, s in definitions
            }
            empreinte = empreinte_suivi(etat)
        avant = suivi.etat_examine if suivi else etat
        ajoutees = [c["libelle"] for ref, c in etat.items() if ref not in avant]
        retirees = [c["libelle"] for ref, c in avant.items() if ref not in etat]
        modifiees = [c["libelle"] for ref, c in etat.items() if ref in avant and c != avant[ref]]
        lire = lien("catalogue_competences", classe.pk, source=ligne["cle"]) if not (
            version and version.pk == adoption.version_id) else lien("catalogue_competences", classe.pk)
        adopter = (lien("referentiel_classe", classe.pk, edition=version.pk, ancre="choisir-referentiel")
                    if courant and version.pk != adoption.version_id and version.pk in autorisees else "")
        lignes.append({**ligne, "reference": reference, "suivi": suivi, "empreinte": empreinte,
                       "ajoutees": ajoutees, "retirees": retirees, "modifiees": modifiees,
                       "lire": lire, "adopter": adopter})
        if reference == cible and action in {"suivre", "marquer-vu"}:
            if action == "marquer-vu" and (not suivi or empreinte != request.POST.get("empreinte")):
                messages.error(request, "Le référentiel a changé. Consultez les nouveautés à nouveau.")
                return redirect(retour)
            if action == "suivre":
                SuiviSourceClasse.objects.get_or_create(classe=classe, reference=reference,
                                                       defaults={"etat_examine": etat})
            else:
                if not SuiviSourceClasse.objects.filter(pk=suivi.pk, etat_examine=avant).update(etat_examine=etat):
                    messages.error(request, "Le suivi a changé. Consultez les nouveautés à nouveau.")
            return redirect(retour)
    from .referentiels import contenu_adoption, contenu_origine
    from .services.heritage_sources import CHAMPS, propositions_suivies

    arbitrages = []
    if adoption and not adoption.clos and suivis:
        principale = {c["id"] for c in contenu_origine(adoption).get("competences", [])}
        ids = [c["id"] for c in contenu_adoption(adoption)["competences"] if c["id"] not in principale]
        for champs in propositions_suivies(classe, ids).values():
            for champ, candidats in champs.items():
                if len({empreinte_suivi(c["valeur"]) for c in candidats}) > 1 or any(c["choisie"] for c in candidats):
                    arbitrages.append({"champ": champ, "libelle": CHAMPS[champ], "candidats": candidats,
                                       "competence": candidats[0]["libelle_competence"]})
    if action == "choisir-heritage":
        choix = request.POST.get("choix", "")
        for arbitrage in arbitrages:
            champ = arbitrage["champ"]
            candidats = arbitrage["candidats"]
            for c in candidats:
                jeton = empreinte_suivi([adoption.pk, champ, c["uuid"], c["source"], c["edition"], c["valeur"]])
                if choix != jeton:
                    continue
                with transaction.atomic():
                    for suivi in SuiviSourceClasse.objects.select_for_update().filter(classe=classe).order_by("pk"):
                        champs = set(suivi.champs_herites.get(c["uuid"], ()))
                        champs.discard(champ)
                        if suivi.reference == f"source-{c['source']}":
                            champs.add(champ)
                        if champs:
                            suivi.champs_herites[c["uuid"]] = sorted(champs)
                        else:
                            suivi.champs_herites.pop(c["uuid"], None)
                        suivi.save(update_fields=["champs_herites"])
                messages.success(request, "Source retenue pour ce champ. Les adaptations locales restent prioritaires.")
                return redirect(retour)
        messages.error(request, "Les propositions ont changé. Consultez-les de nouveau.")
        return redirect(retour)
    for arbitrage in arbitrages:
        for c in arbitrage["candidats"]:
            c["jeton"] = empreinte_suivi([adoption.pk, arbitrage["champ"], c["uuid"], c["source"], c["edition"], c["valeur"]])
    if request.method == "POST":
        if action == "ne-plus-suivre":
            SuiviSourceClasse.objects.filter(classe=classe, reference=cible).delete()
            return redirect(retour)
        raise Http404
    catalogues = {
        identifiant_source_ecole(ecole, identite_grist(catalogue["url"], referentiel["reference"])):
            (catalogue["url"], catalogue["nom"])
        for catalogue in catalogues_grist_connus(ecole.catalogues_referentiels).values()
        for referentiel in catalogue["referentiels"]
    }
    from .models import PartageGristClasse, ReceptionReferentielGrist

    partage_grist = None
    document_espace = ""
    if partage_grist_disponible():
        partage_grist = PartageGristClasse.objects.filter(classe=classe, actif=True).first()
        if partage_grist:
            document_espace = adresse_grist(partage_grist.url)[1]
    documents = {}
    for source_id, document in ReceptionReferentielGrist.objects.filter(
            source_id__in={ligne["version"].source_id for ligne in lignes if ligne["version"]}
    ).order_by("document_grist").values_list("source_id", "document_grist"):
        documents.setdefault(source_id, []).append(document)
    noms_espaces = {}
    for partage in PartageGristClasse.objects.filter(classe__ecole=ecole).exclude(nom_espace=""):
        noms_espaces[adresse_grist(partage.url)[1]] = partage.nom_espace
    if partage_grist and partage_grist.nom_espace:
        noms_espaces[document_espace] = partage_grist.nom_espace
    recus_espace = [ligne for ligne in lignes if document_espace and ligne["version"]
                    and document_espace in documents.get(ligne["version"].source_id, ())]
    ancre_espace = "referentiels-espace-" + document_espace
    espace_demande = bool(document_espace and request.GET.get("groupe") == document_espace)
    groupes = {}
    for ligne in lignes:
        if ligne["suivi"]:
            continue
        version = ligne["version"]
        if version and version.contenu.get("origine") == "etat_initial_repris":
            continue
        for document in documents.get(version.source_id, ()) if version else ():
            cle = "referentiels-espace-" + document
            groupes.setdefault(cle, {
                "nom": noms_espaces.get(document, "Référentiels reçus d’un espace de partage"),
                "ancre": cle, "ouvrir": request.GET.get("groupe") == document, "lignes": [],
            })["lignes"].append(ligne)
        if version and version.source_id in documents:
            continue
        if ligne["autre"]:
            cle, nom = "classes", "Référentiels des classes de l’école"
        elif version.source.identifiant_diffusion.startswith("classe-grist-"):
            cle, nom = "espace-grist", "Référentiels reçus de l’espace Grist"
        elif version.source.identifiant in catalogues:
            cle, nom = catalogues[version.source.identifiant]
        elif version.source.ecole_id:
            cle, nom = "ecole", "Catalogue de l’école"
        else:
            cle, nom = "instance", "Catalogue Petits Pas"
        groupes.setdefault(cle, {"nom": nom, "lignes": []})["lignes"].append(ligne)
    if espace_demande:
        groupes[ancre_espace] = {"nom": noms_espaces.get(document_espace, "Espace de partage"),
                                 "ancre": ancre_espace, "ouvrir": True, "lignes": recus_espace}
    return render(request, "suivi/suivis_referentiels_classe.html",
                  {"classe": classe, "lignes": [ligne for ligne in lignes if ligne["suivi"]],
                   "adoption": adoption, "a_des_suivis": bool(suivis),
                   "arbitrages": arbitrages,
                   "divergences": [l for l in divergences.values() if len({c["signature"] for c in l}) > 1],
                   "ouvrir_espace": request.GET.get("espace") == "1",
                   "recus_espace": bool(recus_espace),
                   "lien_referentiels_espace": (
                       lien("suivis_referentiels_classe", classe.pk, decouvrir=1, groupe=document_espace,
                            ancre=ancre_espace) if document_espace else ""),
                   "ouvrir_decouverte": espace_demande or not suivis or request.GET.get("decouvrir") == "1",
                   "classe_active": classe.etat == classe.ACTIVE, "groupes": list(groupes.values()),
                   "peut_gerer_catalogues": autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole),
                   "peut_importer_ecole": autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, classe),
                   "indisponibles": set(suivis) - disponibles.keys(), "partage_grist": partage_grist})
