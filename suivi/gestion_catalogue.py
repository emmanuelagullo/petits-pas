"""Actions de classement et de visibilité du catalogue de classe."""
from urllib.parse import parse_qsl, urlsplit

from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect

from .autorisations import GERER_REFERENTIEL_CLASSE, MODIFIER_ETAT, autorise
from .forms_referentiels import DeplacementCompetenceForm
from .models import AdaptationCompetence, Competence
from .navigation import lien
from .referentiels import adoption_courante, contenu_adoption
from .rubriques import contenu_classement
from .services.adaptations_referentiels import enregistrer_adaptation
from .suivi_libre import est_libre


def choix_gestion(request, classe, identifiant):
    adoption = adoption_courante(classe)
    if not adoption or adoption.clos or not autorise(request.user, GERER_REFERENTIEL_CLASSE, classe):
        raise PermissionDenied
    contenu = contenu_adoption(adoption)
    definition = next((c for c in contenu["competences"] if str(c["id"]) == identifiant), None)
    if definition is None:
        raise Http404
    competence = Competence.objects.get(pk=definition["id"])
    if est_libre(competence) and not autorise(request.user, MODIFIER_ETAT, classe):
        raise PermissionDenied
    regle = AdaptationCompetence.objects.filter(classe=classe, competence=competence).first()
    return adoption, contenu, definition, competence, regle


def deplacer(request, classe, identifiant, retour):
    adoption, position, definition, competence, regle = choix_gestion(request, classe, identifiant)
    choix = contenu_classement(adoption)
    domaines = {d["id"]: d["nom"] for d in choix["domaines"]}
    groupes = {s["id"]: s["nom"] for s in choix["sous_domaines"]}
    domaine_actuel = next((d["nom"] for d in position["domaines"] if d["id"] == definition["domaine_id"]), "")
    groupe_actuel = next((s["nom"] for s in position["sous_domaines"] if s["id"] == definition["sous_domaine_id"]), "")
    revision = regle.revision if regle else 0
    attendu = [request.user.pk, classe.pk, adoption.pk, competence.pk, revision]
    form = DeplacementCompetenceForm(
        request.POST if request.method == "POST" else None,
        initial={"domaine": definition["domaine_id"], "sous_domaine": definition["sous_domaine_id"]},
        **choix)
    if request.method == "POST" and form.is_valid():
        try:
            if signing.loads(request.POST.get("jeton", ""), salt="deplacer-catalogue", max_age=1800) != attendu:
                raise ValidationError("Le classement a changé. Rechargez le formulaire.")
            domaine, groupe = (form.cleaned_data[cle] for cle in ("domaine", "sous_domaine"))
            enregistrer_adaptation(utilisateur=request.user, ecole=classe.ecole, annee=classe.annee_scolaire,
                classe=classe, competence=competence, libelle=regle.libelle if regle else None,
                visible=regle.visible if regle else None, adoption_attendue=adoption.pk,
                revision_attendue=revision, destination=(domaine, groupe), depuis_catalogue=True)
        except signing.BadSignature:
            form.add_error(None, "Le formulaire a expiré. Rechargez-le.")
        except ValidationError as cause:
            form.add_error(None, cause)
        else:
            nom_domaine, nom_groupe = domaines[domaine], groupes.get(groupe, "")
            messages.success(request, "Déplacée vers " + " → ".join(filter(None, (nom_domaine, nom_groupe))) + ".")
            parametres = dict(parse_qsl(urlsplit(retour).query))
            if ((parametres.get("domaine") and parametres["domaine"] != nom_domaine)
                    or (parametres.get("sous_domaine") and parametres["sous_domaine"] != nom_groupe)
                    or parametres.get("classement") or parametres.get("groupe")):
                route = "choisir_competence" if urlsplit(retour).path == lien("choisir_competence", classe.pk) else "catalogue_competences"
                retour = lien(route, classe.pk, **parametres, deplace=competence.pk)
            return redirect(retour)
    return {"form": form, "competence": definition, "domaine": domaine_actuel, "groupe": groupe_actuel,
            "retour": retour, "jeton": signing.dumps(attendu, salt="deplacer-catalogue")}


def changer_visibilite(request, classe, retour):
    _, _, _, competence, regle = choix_gestion(request, classe, request.POST.get("competence", ""))
    valeur = request.POST.get("visibilite")
    if valeur not in ("masquer", "reafficher"):
        raise PermissionDenied
    try:
        enregistrer_adaptation(utilisateur=request.user, ecole=classe.ecole, annee=classe.annee_scolaire,
            classe=classe, competence=competence, libelle=regle.libelle if regle else None,
            visible=valeur == "reafficher", adoption_attendue=int(request.POST.get("adoption", "")),
            revision_attendue=int(request.POST.get("revision", "")), depuis_catalogue=True)
    except ValueError:
        messages.error(request, "Rechargez le catalogue avant de changer la visibilité.")
    except ValidationError as cause:
        messages.error(request, " ".join(cause.messages))
    else:
        messages.success(request, "Compétence masquée." if valeur == "masquer" else "Compétence réaffichée.")
    return redirect(retour)
