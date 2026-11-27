"""Découverte et suivi des référentiels à l’échelle d’une école."""
import hashlib
import json
import re
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
                            VOIR_SUIVI, autorise, charger_classe_autorisee)
from .contexte_ecole import ecole_courante
from .identites_referentiels import identifiant_source_classe, identifiant_source_ecole
from .models import ChoixApplicationAnnuel, DestinationPublicationGrist, Ecole, VersionReferentiel, annee_scolaire_pour
from .navigation import lien
from .services.catalogue_fourni import REFERENTIELS_DEPART
from .services.identites_grist import classes_grist_locales
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


def enregistrer_catalogue(ecole, utilisateur, cle, *, catalogue=None, reference=None, suivre=False, suivre_catalogue=None, suivi_initial=None):
    with transaction.atomic():
        ecole = Ecole.objects.select_for_update().get(pk=ecole.pk)
        if not autorise(utilisateur, GERER_REFERENTIEL_ECOLE, ecole):
            raise PermissionDenied
        initial = {"suivre_catalogue": suivi_initial} if suivi_initial is not None else {}
        etat = ecole.catalogues_referentiels.setdefault(cle, initial)
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


def modifier_catalogue_classe(request, classe, catalogues, url_saisie, suivi_initial):
    action = request.POST.get("action")
    cle = request.POST.get("catalogue", "")
    contenu = None
    if action == "ajouter":
        contenu = lire_catalogue_grist(url_saisie)
        contenu["lien"] = url_saisie.strip()
        cle = contenu["url"]
    elif action in {"actualiser-catalogue", "modifier-lien-catalogue"} and catalogues.get(cle, {}).get("url"):
        precedent = catalogues[cle]
        adresse = url_saisie.strip() if action == "modifier-lien-catalogue" else precedent.get("lien", cle)
        if action == "modifier-lien-catalogue" and adresse_grist(adresse)[1] != adresse_grist(cle)[1]:
            raise ValidationError("Ce lien désigne un autre document. Utilisez « Ajouter un catalogue » pour le consulter.")
        contenu = lire_catalogue_grist(adresse)
        if adresse_grist(contenu["url"])[1] != adresse_grist(cle)[1]:
            raise ValidationError("L’adresse du catalogue a changé.")
        contenu.update(url=cle, lien=adresse)
        if contenu["nom"].strip().casefold() in {"untitled document", "document sans titre", "sans titre"}:
            contenu["nom"] = precedent["nom"]
        if cle in catalogues_grist_connus({}):
            contenu["essai"] = True
    elif action not in {"suivre-catalogue", "ne-plus-suivre-catalogue", "heriter-catalogue"} or not catalogues.get(cle, {}).get("url"):
        raise ValidationError("Choisissez un catalogue connu de la classe.")
    with transaction.atomic():
        classe = type(classe).objects.select_for_update().get(pk=classe.pk)
        if classe.etat != classe.ACTIVE or not autorise(request.user, GERER_REFERENTIEL_CLASSE, classe):
            raise PermissionDenied
        etat = classe.catalogues_propres.setdefault(cle, {})
        herite = cle in classe.ecole.catalogues_referentiels or cle in catalogues_grist_connus({})
        if contenu is not None:
            if action in {"actualiser-catalogue", "modifier-lien-catalogue"} or not herite:
                etat["catalogue"] = contenu
            if action == "ajouter" and not herite:
                etat.setdefault("suivre_catalogue", suivi_initial)
        elif action == "heriter-catalogue":
            if not herite:
                raise ValidationError("Ce catalogue n’est pas proposé par l’école.")
            classe.catalogues_propres.pop(cle, None)
        else:
            etat["suivre_catalogue"] = action == "suivre-catalogue"
        if not etat:
            classe.catalogues_propres.pop(cle, None)
        classe.save(update_fields=["catalogues_propres"])
    if action == "actualiser-catalogue":
        from .services.actualisation_catalogues import actualiser_editions_connues

        actualiser_editions_connues(request.user, classe, contenu, manuelle=True)
    return cle, contenu


@acces_requis
@require_http_methods(["GET", "POST"])
def decouvrir_referentiels(request, *, examen_echange=None):
    from .services.catalogues_externes import reglages_catalogues_classe
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
    gestion_classe = bool(classe and request.GET.get("gestion") == "classe")
    if gestion_classe:
        navigation["gestion"] = "classe"
        if classe.etat != classe.ACTIVE:
            raise PermissionDenied
    if not gestion_classe and not peut_gerer and (classe is None or request.method == "POST"):
        raise PermissionDenied
    retour = lien("decouvrir_referentiels", annee=annee, q=q, filtre=filtre, **navigation)
    contexte = {"annee": annee, "q": q, "filtre": filtre, "retour": retour,
                "depuis_echange": navigation.get("depuis") == "echange",
                "classe_origine": classe, "peut_gerer": peut_gerer, "suivi_initial": True,
                "depuis_classe": bool(classe), "gestion_classe": gestion_classe,
                "examen_grist": lien("paquets_referentiels_ecole", annee=annee, origine="decouverte",
                                     q=q, filtre=filtre, **navigation),
                "peut_importer": autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, ecole)}
    if gestion_classe:
        contexte.update(peut_importer=True, examen_grist=lien(
            "paquets_referentiels_classe", classe.pk, volet="importer", destination="classe", depuis="decouverte", ancre="import-referentiel",
        ))
    invitation = request.GET.get("catalogue_invite", "")
    if invitation and (peut_gerer or gestion_classe):
        try:
            adresse_grist(invitation)
        except ValidationError as cause:
            contexte["erreur"] = " ".join(cause.messages)
        else:
            contexte["url_saisie"] = invitation
            contexte["invitation_catalogue"] = True
    instance = catalogue_instance(annee)
    regles = reglages_catalogues_classe(classe) if gestion_classe else ecole.catalogues_referentiels
    catalogues = catalogues_visibles(regles, instance)
    if request.method == "POST" and gestion_classe and request.POST.get("action") == "actualiser-automatiquement":
        from django.core.cache import cache
        from django.http import JsonResponse
        from .services.actualisation_catalogues import actualiser_catalogues_classe

        if not cache.add(f"catalogues-classe-{classe.pk}", True, timeout=300):
            return JsonResponse({"editions": 0, "erreurs": []})
        nombre, erreurs = actualiser_catalogues_classe(request.user, classe)
        return JsonResponse({"editions": nombre, "erreurs": erreurs})
    if request.method == "POST" and gestion_classe:
        try:
            contexte["url_saisie"] = request.POST.get("url", "")[:2000]
            contexte["suivi_initial"] = request.POST.get("suivre_catalogue") == "oui"
            _, contenu = modifier_catalogue_classe(
                request, classe, catalogues, contexte["url_saisie"], contexte["suivi_initial"],
            )
            classe.refresh_from_db(fields=["catalogues_propres"])
            regles = reglages_catalogues_classe(classe)
            contexte.update(catalogue_ajoute=contenu, message="Catalogues de la classe mis à jour.")
        except ValidationError as erreur:
            contexte["erreur"] = " ".join(erreur.messages)
    elif request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "ajouter":
                contexte["url_saisie"] = request.POST.get("url", "")[:2000]
                contexte["suivi_initial"] = request.POST.get("suivre_catalogue") == "oui"
                catalogue = lire_catalogue_grist(contexte["url_saisie"])
                ecole = enregistrer_catalogue(ecole, request.user, catalogue["url"], catalogue=catalogue,
                                               suivi_initial=contexte["suivi_initial"])
                contexte.update(catalogue_ajoute=catalogue, message="Catalogue disponible pour l’école.")
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

    if not gestion_classe:
        regles = ecole.catalogues_referentiels
    versions = {}
    for identifiant, numero in VersionReferentiel.objects.filter(
            Q(source__ecole=ecole) | Q(source__ecole__isnull=True),
            Q(source__classe_privee__isnull=True) | Q(source__classe_privee=classe if gestion_classe else None),
    ).values_list(
            "source__identifiant", "numero").order_by("pk"):
        versions.setdefault(identifiant, []).append(numero)
    autorisees = {version.pk for version in choix_bases(ecole, annee).versions}
    groupes = []
    contexte["a_des_suivis"] = any(catalogue.get("url") and catalogue_suivi(regles.get(cle, {}))
                                   for cle, catalogue in catalogues_visibles(regles, instance).items())
    texte_recherche = slugify(q)
    termes = texte_recherche.split("-") if texte_recherche else []
    classes_locales = classes_grist_locales(ecole)
    for cle, catalogue in catalogues_visibles(regles, instance).items():
        lignes = []
        ajoute = (contexte.get("catalogue_ajoute") or {}).get("url") == cle
        for source in catalogue["referentiels"]:
            reference = source["reference"]
            url = catalogue.get("url")
            identifiant = identifiant_source_ecole(ecole, identite_grist(url, reference)) if url else source["identifiant_local"]
            locales = versions.get(identifiant, [])
            if url and gestion_classe:
                locales = sorted(set(locales) | set(versions.get(
                    identifiant_source_classe(classe, identite_grist(url, reference)), [],
                )))
            derniere = source["editions"][0]
            suivi = reference in regles.get(cle, {}).get("suivis", ())
            mise_a_jour = bool(url and locales) and str(derniere) not in locales
            ligne = {**source, "cle": cle, "url": url,
                     "deja_local": source.get("contenu_courant") and reference in classes_locales,
                     "nouveau": (cle, reference) in contexte.get("nouveautes", ()),
                     "suivi": suivi, "locales": locales, "derniere": derniere, "mise_a_jour": mise_a_jour,
                     "locale": str(derniere) in locales}
            version_consultable = next((version for version in source.get("versions_instance", ())
                                        if version.pk in autorisees), None)
            if version_consultable and peut_gerer:
                ligne["consultation"] = lien("consulter_referentiels_ecole", annee=annee,
                                             version=version_consultable.pk, origine="decouverte",
                                             q_catalogue=q, filtre_catalogue=filtre, **navigation)
                ligne["edition_consultable"] = version_consultable.numero
            if ligne["nouveau"] or ajoute or (all(terme in slugify(f'{source["titre"]} {catalogue["nom"]}') for terme in termes)
                          and (filtre != "suivis" or suivi) and (filtre != "mises-a-jour" or mise_a_jour)):
                lignes.append(ligne)
        if ajoute or lignes or (not q and not filtre):
            groupes.append({"nom": catalogue["nom"], "url": catalogue.get("url"), "lignes": lignes,
                            "cle": cle, "suivi": (bool(regles.get(cle, {}).get("suivre_catalogue")) if gestion_classe
                                                 else catalogue_suivi(regles.get(cle, {}))),
                            "herite": gestion_classe and (cle in ecole.catalogues_referentiels or cle in catalogues_grist_connus({})),
                            "personnalise": gestion_classe and cle in classe.catalogues_propres})
    contexte["actualisation_active"] = gestion_classe and any(
        etat.get("suivre_catalogue") and etat.get("catalogue", {}).get("url") for etat in regles.values()
    )
    contexte.update(groupes=groupes, nombre_resultats=sum(len(groupe["lignes"]) for groupe in groupes))
    contexte["examen_echange"] = examen_echange
    return render(request, "suivi/decouvrir_referentiels.html", contexte)


def empreinte_suivi(valeur):
    return hashlib.sha256(json.dumps(valeur, sort_keys=True).encode()).hexdigest()


@acces_requis
@require_http_methods(["GET", "POST"])
def suivis_classe(request, classe_pk, contexte_espace=None, *, examen_echange=None):
    from .models import SuiviSourceClasse
    from .referentiels import adoption_courante
    from .services.sources_catalogue import cle_source_ajout, lignes_source, sources_catalogue

    ecole = ecole_courante(request)
    classe = charger_classe_autorisee(request.user, classe_pk, GERER_REFERENTIEL_CLASSE, ecole=ecole)
    from .services.catalogues_externes import reglages_catalogues_classe

    reglages = reglages_catalogues_classe(classe)
    distants = catalogues_grist_connus(reglages)
    contexte_catalogue = {"suivi_initial": True}
    invitation_catalogue = request.GET.get("catalogue_invite", "")[:2000]
    if classe.etat == classe.ACTIVE and invitation_catalogue:
        contexte_catalogue.update(url_saisie=invitation_catalogue, ouvrir_ajout=True)
    action_catalogue = request.POST.get("action") if contexte_espace is None else None
    catalogue_poste = action_catalogue in {
        "ajouter", "actualiser-catalogue", "modifier-lien-catalogue", "suivre-catalogue", "ne-plus-suivre-catalogue", "heriter-catalogue",
    }
    groupe_poste = ""
    if catalogue_poste:
        if classe.etat != classe.ACTIVE:
            raise PermissionDenied
        url_saisie = request.POST.get("url", "")[:2000]
        suivi_initial = request.POST.get("suivre_catalogue") == "oui"
        cle = request.POST.get("catalogue", "")
        try:
            cle, contenu = modifier_catalogue_classe(request, classe, distants, url_saisie, suivi_initial)
        except ValidationError as erreur:
            contexte_catalogue["erreur"] = " ".join(erreur.messages)
            contexte_catalogue.update(url_saisie=url_saisie, suivi_initial=suivi_initial,
                                      ouvrir_ajout=action_catalogue == "ajouter",
                                      erreur_ajout=action_catalogue == "ajouter")
        else:
            statut = "Catalogue actualisé." if action_catalogue == "actualiser-catalogue" else "Catalogue enregistré."
            request.session[f"catalogue-resultat-{classe.pk}"] = (cle, statut)
            ancre = "catalogue-" + hashlib.sha256(cle.encode()).hexdigest()[:12]
            if action_catalogue == "ajouter":
                from .models import PartageGristClasse

                partage_actif = PartageGristClasse.objects.filter(classe=classe, actif=True).first()
                document = adresse_grist(cle)[1]
                if partage_actif and adresse_grist(partage_actif.url)[1] == document:
                    ancre = "referentiels-espace-" + document
            return redirect(lien("suivis_referentiels_classe", classe.pk, catalogue=ancre, ancre=ancre))
        groupe_poste = cle
    resultat_catalogue = request.session.pop(f"catalogue-resultat-{classe.pk}", None)
    adoption = adoption_courante(classe)
    autorisees = {v.pk for v in choix_bases(ecole, classe.annee_scolaire).versions}
    retour = lien("suivis_referentiels_classe", classe.pk, ancre="referentiels-suivis")
    groupe_retour = request.GET.get("catalogue", "")
    if groupe_retour and re.fullmatch(r"catalogue-[a-f0-9]{12}|referentiels-espace-[A-Za-z0-9_-]{8,64}", groupe_retour):
        retour = lien("suivis_referentiels_classe", classe.pk, catalogue=groupe_retour,
                      ancre="referentiel-" + request.POST.get("source", "")[:64])
    disponibles = {}
    if adoption and not adoption.clos:
        sources = sources_catalogue(request.user, classe, adoption)
        sources[f"version-{adoption.version_id}"] = (
            adoption.version.source.titre, adoption.version, None)
        for cle, (titre, version, autre) in sources.items():
            reference = cle_source_ajout(version, autre)
            ligne = disponibles.get(reference)
            if ligne and version.pk <= ligne["version"].pk:
                continue
            disponibles[reference] = {"cle": cle, "titre": titre, "version": version, "autre": autre}

    suivis = {s.reference: s for s in SuiviSourceClasse.objects.filter(classe=classe)}
    action = request.POST.get("action") if contexte_espace is None else None
    cible = request.POST.get("source")
    if action in {"ecarter-ajout", "proposer-ajout"}:
        if cible not in disponibles or (adoption and cible == f"source-{adoption.version.source_id}"):
            raise Http404
        with transaction.atomic():
            cible_classe = type(classe).objects.select_for_update().get(pk=classe.pk)
            ecartees = set(cible_classe.sources_ajout_ecartees)
            if action == "ecarter-ajout":
                ecartees.add(cible)
            else:
                ecartees.discard(cible)
            cible_classe.sources_ajout_ecartees = sorted(ecartees)
            cible_classe.save(update_fields=["sources_ajout_ecartees"])
        return redirect(retour)
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
            courant) else lien("catalogue_competences", classe.pk)
        adopter = (lien("referentiel_classe", classe.pk, edition=version.pk, ancre="choisir-referentiel")
                    if courant and version.pk != adoption.version_id and version.pk in autorisees else "")
        lignes.append({**ligne, "titre": adoption.version.source.titre if courant else ligne["titre"],
                       "reference": reference, "suivi": suivi, "empreinte": empreinte,
                       "ajoutees": ajoutees, "retirees": retirees, "modifiees": modifiees,
                       "lire": lire, "adopter": adopter, "courant": courant,
                       "ecartee": reference in classe.sources_ajout_ecartees})
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
                candidats = [c for c in candidats if f"source-{c['source']}" in suivis]
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
                    from .audit import journaliser

                    journaliser(request.user, "referentiel.choix_heritage", classe, nouvelles={
                        "competence": c["libelle_competence"], "champ": arbitrage["libelle"],
                        "source": c["titre"], "edition": c["edition"],
                    })
                messages.success(request, "Source retenue pour ce champ. Les adaptations locales restent prioritaires.")
                return redirect(retour)
        messages.error(request, "Les propositions ont changé. Consultez-les de nouveau.")
        return redirect(retour)
    for arbitrage in arbitrages:
        for c in arbitrage["candidats"]:
            c["jeton"] = empreinte_suivi([adoption.pk, arbitrage["champ"], c["uuid"], c["source"], c["edition"], c["valeur"]])
    if request.method == "POST" and not catalogue_poste and contexte_espace is None:
        if action == "ne-plus-suivre":
            SuiviSourceClasse.objects.filter(classe=classe, reference=cible).delete()
            return redirect(retour)
        raise Http404
    from pwa.partage_grist import contexte_raccordement
    from .models import PartageGristClasse, ReceptionReferentielGrist

    espace_disponible = classe.etat == classe.ACTIVE and partage_grist_disponible()
    partage_grist = PartageGristClasse.objects.filter(classe=classe).first() if espace_disponible else None
    document_espace = adresse_grist(partage_grist.url)[1] if partage_grist else ""
    if partage_grist and partage_grist.actif and partage_grist.editions_catalogue is not None:
        url_espace = next((url for url in distants if adresse_grist(url)[1] == document_espace), partage_grist.url)
        catalogue_espace = distants.get(url_espace, {})
        courants = [source for source in catalogue_espace.get("referentiels", []) if source.get("contenu_courant")]
        distants[url_espace] = {**catalogue_espace, "url": url_espace, "nom": partage_grist.nom_espace,
                                "referentiels": [*courants, *partage_grist.editions_catalogue]}
    catalogues = {
        identifiant(portee, identite_grist(url, referentiel["reference"])): (url, catalogue["nom"], referentiel)
        for url, catalogue in distants.items()
        for referentiel in catalogue["referentiels"]
        for identifiant, portee in ((identifiant_source_ecole, ecole), (identifiant_source_classe, classe))
    }
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
    classes_locales = classes_grist_locales(ecole)
    liens_classes = {ligne["autre"].classe_id: ligne["lire"] for ligne in lignes if ligne["autre"]}
    recus_espace = [ligne for ligne in lignes if document_espace and ligne["version"]
                    and document_espace in documents.get(ligne["version"].source_id, ())]
    nombre_recus_espace = len(recus_espace)
    ancre_espace = "referentiels-espace-" + document_espace
    espace_demande = bool(document_espace and request.GET.get("groupe") == document_espace)
    groupes = {}
    for ligne in lignes:
        version = ligne["version"]
        if version and not ligne["courant"] and version.source.identifiant_diffusion in classes_locales:
            continue
        if version and version.contenu.get("origine") == "etat_initial_repris":
            continue
        for document in (sorted(documents.get(version.source_id, ()), key=lambda d: d != document_espace)[:1] if version else ()):
            cle = "referentiels-espace-" + document
            groupes.setdefault(cle, {
                "nom": noms_espaces.get(document, "Référentiels reçus d’un espace de partage"),
                "ancre": cle, "ouvrir": request.GET.get("groupe") == document, "lignes": [],
            })["lignes"].append(ligne)
        if version and version.source_id in documents:
            continue
        if ligne["autre"]:
            cle, nom = "classes", ("Autres classes dans ce Petits Pas" if settings.MODE_LOCAL or getattr(settings, "MODE_PWA", False) else "Autres classes de l’école")
        elif version.source.identifiant_diffusion.startswith("classe-grist-"):
            cle, nom = "espace-grist", "Référentiels reçus de l’espace Grist"
        elif version.source.identifiant in catalogues:
            cle, nom, _ = catalogues[version.source.identifiant]
        elif version.source.classe_privee_id:
            cle, nom = "classe", "Catalogue de la classe"
        elif version.source.ecole_id:
            cle, nom = "ecole", "Catalogue de l’école"
        else:
            cle, nom = "instance", "Catalogue Petits Pas"
        groupes.setdefault(cle, {"nom": nom, "lignes": []})["lignes"].append(ligne)
    for url, catalogue in distants.items():
        rattache = bool(document_espace and adresse_grist(url)[1] == document_espace)
        if rattache:
            for ancienne in groupes.pop(url, {}).get("lignes", []):
                if ancienne not in recus_espace:
                    recus_espace.append(ancienne)
        groupe = ({"lignes": recus_espace} if rattache else
                  groupes.setdefault(url, {"nom": catalogue["nom"], "lignes": []}))
        references = {catalogues[ligne["version"].source.identifiant][2]["reference"]: ligne
                      for ligne in groupe["lignes"] if ligne.get("version") and ligne["version"].source.identifiant in catalogues}
        groupe.update(url=url, lien=catalogue.get("lien", url), essai=bool(catalogue.get("essai")),
                      suivi=bool(reglages.get(url, {}).get("suivre_catalogue")),
                      lien_saisi=url_saisie if action_catalogue == "modifier-lien-catalogue" and groupe_poste == url else "",
                      erreur_lien=action_catalogue == "modifier-lien-catalogue" and groupe_poste == url,
                      herite=url in ecole.catalogues_referentiels or url in catalogues_grist_connus({}),
                      personnalise=url in classe.catalogues_propres)
        for source in catalogue["referentiels"]:
            ligne = references.get(source["reference"])
            classe_locale = classes_locales.get(source["reference"]) if source.get("contenu_courant") else None
            if classe_locale:
                groupe["lignes"].append({**source, "deja_local": True, "classe_propre": classe_locale == classe.pk,
                                         "courant": False, "lire_locale": liens_classes.get(classe_locale, "")})
                continue
            if rattache and source.get("contenu_courant"):
                continue
            edition = source["editions"][0]
            distant = {**source, "url": catalogue.get("lien", url), "derniere": edition}
            if ligne is None:
                groupe["lignes"].append({**distant, "courant": False, "edition_distante": distant})
            elif str(edition) != str(ligne["version"].numero).split("-", 1)[0]:
                ligne["edition_distante"] = {**distant, "mise_a_jour": True}
            if ligne is not None:
                ligne["selection_exportee"] = source["reference"].startswith("selection-")
                if source.get("contenu_courant"):
                    ligne["contenu_courant"] = True
                if source.get("origine_classe_grist"):
                    ligne["origine_classe_grist"] = source["origine_classe_grist"]
    for groupe in [*groupes.values(), {"lignes": recus_espace}]:
        courants = {}
        editions_liees = []
        for ligne in groupe["lignes"]:
            distante = ligne.get("edition_distante", ligne)
            version = ligne.get("version")
            reference_courante = version.source.identifiant_diffusion if version else distante.get("reference", "")
            if reference_courante.startswith("classe-grist-"):
                courants[reference_courante] = ligne
            if distante.get("origine_classe_grist"):
                editions_liees.append((ligne, distante))
        for ligne, distante in editions_liees:
            courante = courants.get(distante["origine_classe_grist"])
            if courante is not None and courante is not ligne:
                courante.setdefault("editions_publiees", []).append(ligne)
                groupe["lignes"].remove(ligne)
    if espace_disponible:
        groupes.pop(ancre_espace, None)
        contexte_espace = contexte_espace or contexte_raccordement(classe, partage_grist)
        groupes[ancre_espace if document_espace else "espace-partage"] = {
            "nom": (partage_grist.nom_espace if partage_grist else "") or "Espace de partage",
            "ancre": ancre_espace if document_espace else "espace-partage",
            "ouvrir": espace_demande or bool(contexte_espace.get("erreur")) or request.GET.get("espace") == "1",
            "espace": contexte_espace, "espace_actif": partage_grist,
            "partiel_resume": "suivi/partiels/resume_espace_grist.html"
                if partage_grist and partage_grist.actif else "",
            "lignes": recus_espace, "nombre_recus": nombre_recus_espace,
        }
    from .models import ContributionReferentielEquipe
    from .services.sources_catalogue import ordre_provenance

    document_equipe = document_espace if partage_grist and partage_grist.actif else ""
    equipe_existante = ContributionReferentielEquipe.objects.filter(
        ecole=ecole, document_grist=document_equipe,
    ).exists()
    for cle, groupe in groupes.items():
        groupe["provenance"] = (
            "classes" if cle == "classes" else
            "espace" if groupe.get("espace") or cle.startswith(("referentiels-espace-", "espace-grist")) else
            "instance" if cle == "instance" else "grist" if groupe.get("url") else "ecole"
        )
    ordre_grist = {url: indice for indice, url in enumerate(distants)}
    groupes = dict(sorted(groupes.items(), key=lambda item: (
        ordre_provenance(item[1]["provenance"]), ordre_grist.get(item[0], 0),
    )))
    for cle, groupe in groupes.items():
        ancre = groupe.setdefault("ancre", "catalogue-" + hashlib.sha256(cle.encode()).hexdigest()[:12])
        nombre = len(groupe["lignes"])
        if groupe.get("url"):
            groupe["resultat"] = resultat_catalogue[1] if resultat_catalogue and resultat_catalogue[0] == cle else ""
            groupe["erreur"] = contexte_catalogue.get("erreur") if groupe_poste == cle else ""
        for ligne in groupe["lignes"]:
            if ligne.get("lire"):
                separateur = "&" if "?" in ligne["lire"] else "?"
                ligne["lire"] += f"{separateur}catalogue_retour={ancre}&source_retour={ligne['reference']}"
        mode = ("Contenu courant" if cle == "classes" else
                "Synchronisation automatique" if cle.startswith("referentiels-espace-") else
                ("Catalogue Grist · Actualisation automatique" if groupe.get("suivi") else "Catalogue Grist · Actualisation manuelle")
                if groupe.get("url") else "Éditions disponibles")
        if groupe.get("espace"):
            partage = groupe["espace"]["partage"]
            if not partage:
                groupe["resume"] = "Aucun espace rejoint"
            elif not partage.actif:
                deja_partage = " · Référentiel toujours partagé" if groupe["espace"]["partage_confirme"] else ""
                groupe["resume"] = f"Synchronisation suspendue{deja_partage} · {nombre} référentiel{'s' if nombre != 1 else ''}"
        groupe.setdefault("resume", f"{nombre} référentiel{'s' if nombre != 1 else ''} · {mode}")
        ecartees = sum(bool(l.get("ecartee")) for l in groupe["lignes"])
        if ecartees and not groupe.get("espace"):
            groupe["resume"] += f" · {ecartees} écarté{'s' if ecartees != 1 else ''} des ajouts"
        groupe["ouvrir"] = groupe.get("ouvrir", False) or ancre == groupe_retour or cle == groupe_poste
    from .publication_grist import historique_publications_classe

    publication_par_document = {}
    for publication in historique_publications_classe(request, classe):
        document = adresse_grist(publication.url)[1]
        publication_par_document.setdefault(document, publication)
    destinations_publication = []
    for document, publication in publication_par_document.items():
        groupe_existant = next((groupe for groupe in groupes.values() if (
            groupe.get("url") and adresse_grist(groupe["url"])[1] == document
        ) or groupe.get("ancre") == "referentiels-espace-" + document), None)
        groupe = groupe_existant if groupe_existant is not None else {
            "nom": publication.nom, "ancre": "publication-" + document, "publication_seule": True,
        }
        groupe["publication"] = publication
        groupe_retour_publication = "destinations-publication" if groupe.get("publication_seule") else groupe["ancre"]
        if autorise(request.user, VOIR_SUIVI, classe):
            groupe["republier"] = lien(
                "catalogue_competences", classe.pk, export=1, catalogue_retour=groupe_retour_publication,
                publication=publication.pk, ancre="partager-competences",
            )
        else:
            groupe["republier"] = lien(
                "paquets_referentiels_classe", classe.pk, interface="export-classe", volet="exporter",
                depuis="catalogues", catalogue=groupe_retour_publication, publication=publication.pk,
                ancre="export-referentiel",
            )
        if groupe_existant is None:
            destinations_publication.append(groupe)

    from .models import EvenementAudit

    decisions = EvenementAudit.objects.filter(ecole=ecole, modele=classe._meta.label_lower,
        objet_id=str(classe.pk), action="referentiel.choix_heritage")[:20]
    historique_auto = sorted(classe.historique_heritage, key=lambda entree: not entree["impact"])
    resume_decisions = ("Propositions à examiner" if arbitrages or any(
        len({c["signature"] for c in l}) > 1 for l in divergences.values()
    ) or set(suivis) - disponibles.keys() else "Historique")
    actualisation = lien("decouvrir_referentiels", annee=classe.annee_scolaire, classe=classe.pk, gestion="classe")
    return render(request, "suivi/suivis_referentiels_classe.html",
                  {"classe": classe, "examen_echange": examen_echange,
                   "url_catalogues": lien("suivis_referentiels_classe", classe.pk),
                   "lignes": [ligne for ligne in lignes if ligne["suivi"]],
                   "adoption": adoption, "a_des_suivis": bool(suivis),
                   "nouvelle_edition": any(l["adopter"] for l in lignes),
                   "arbitrages": arbitrages, "decisions": decisions, "historique_auto": historique_auto,
                   "resume_decisions": resume_decisions,
                   "divergences": [l for l in divergences.values() if len({c["signature"] for c in l}) > 1],
                   "catalogue_formulaire": contexte_catalogue,
                   "actualisation": actualisation if classe.etat == classe.ACTIVE and any(
                       etat.get("suivre_catalogue") and etat.get("catalogue", {}).get("url")
                       for etat in reglages.values()) else "",
                   "classe_active": classe.etat == classe.ACTIVE,
                   "groupes": list(groupes.values()), "destinations_publication": destinations_publication,
                   "ouvrir_destinations_publication": groupe_retour == "destinations-publication", "equipe_existante": equipe_existante,
                   "peut_gerer_catalogues": autorise(request.user, GERER_REFERENTIEL_ECOLE, ecole),
                   "peut_importer_ecole": autorise(request.user, IMPORTER_REFERENTIEL_ECOLE, classe),
                   "indisponibles": set(suivis) - disponibles.keys()},
                  status=400 if contexte_catalogue.get("erreur") or (contexte_espace or {}).get("erreur") else 200)
