"""Les Cerfs-volants : exemple fictif commun à Render, PWA et bureau."""
from datetime import date
from io import BytesIO
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from comptes.models import AffectationClasse, AppartenanceEcole
from .configuration_demo import charger_configuration_demo
from .models import Classe, Eleve, Scolarite
from .services.adoption_bases_referentiels import apercu_adoption, adopter_base
from .services.import_sources_referentiels import importer_source
from .services.suivi_libre import ajouter_reussite, associer
from .services.traces_communes import personnaliser
from .services.pedagogie import enregistrer_trace


def image_realisation(nom):
    # Schéma fictif d'une réalisation ; aucune photographie d'enfant.
    image = Image.new("RGB", (640, 360), "#fff8ed")
    dessin = ImageDraw.Draw(image)
    for i, couleur in enumerate(("#c45c36", "#3a7e88", "#ddad39") * 3):
        x = 22 + i * 67
        dessin.rectangle((x, 125, x + 48, 195), fill=couleur)
    flux = BytesIO(); image.save(flux, "JPEG", quality=85)
    return ContentFile(flux.getvalue(), name=nom)


def preparer_suivi_libre(ecole, utilisateurs):
    configuration = charger_configuration_demo(settings.BASE_DIR / "site/data/demonstration.yaml")
    specification = configuration["classes"]["cerfs_volants"]
    call_command("preparer_suivi_libre", annee=specification["annee_scolaire"], verbosity=0)
    version = importer_source((settings.BASE_DIR / "referentiel/structure-cycle1.yaml").read_text())[0]
    classe = Classe.objects.create(ecole=ecole, nom=specification["nom"],
        annee_scolaire=specification["annee_scolaire"], ordre=7)
    responsable = utilisateurs["remi"]
    AffectationClasse.objects.create(classe=classe,
        appartenance=AppartenanceEcole.objects.get(ecole=ecole, utilisateur=responsable),
        type=AffectationClasse.RESPONSABLE, date_debut=date(2026, 9, 1), attribue_par=utilisateurs["diane"])
    classe.activer()
    apercu = apercu_adoption(utilisateur=responsable, classe=classe, version_id=version.pk)
    adoption = adopter_base(utilisateur=responsable, classe=classe, version_id=version.pk,
        revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
        garde_attendue=apercu["garde"]["empreinte"])
    eleves = []
    for i, prenom in enumerate(("Mila", "Inès", "Noé", "Sami", "Ana", "Zoé")):
        enfant = Eleve.objects.create(ecole=ecole, prenom=prenom, nom="Fictif", annee_naissance=2023)
        Scolarite.objects.create(eleve=enfant, classe=classe, annee_scolaire=classe.annee_scolaire, niveau="PS")
        eleves.append(enfant)
    domaines = {d["code"]: d["id"] for d in adoption.contenu["domaines"]}
    sous = {s["code"]: s["id"] for s in adoption.contenu["sous_domaines"]}
    commun = dict(utilisateur=responsable, classe=classe, niveau="PS", date_observation=date(2026, 10, 1),
                  adoption_attendue=adoption.pk)
    ajouter_reussite(ids=[eleves[0].pk], domaine_id=domaines["LANG"], sous_domaine_id=sous["ORAL"],
        libelle="Je raconte les étapes de ma construction", **commun)
    ajouter_reussite(ids=[eleves[2].pk], domaine_id=domaines["ARTS"],
        libelle="Je compose une réalisation avec plusieurs couleurs", photo=image_realisation("composition-fictive.jpg"), **commun)
    groupe = ajouter_reussite(ids=[e.pk for e in eleves[1:4]], domaine_id=domaines["MATH"],
        sous_domaine_id=sous["FORMES"], libelle="Je poursuis une alternance de trois couleurs",
        commentaire="<prenom> poursuit la suite de couleurs.", photo=image_realisation("suite-fictive.jpg"), **commun)
    trace = groupe.competence.traces_communes.get().attributions.get(observation__eleve=eleves[3])
    personnelle = personnaliser(utilisateur=responsable, trace=trace)
    enregistrer_trace(utilisateur=responsable, eleve=eleves[3], competence=groupe.competence,
        scolarite=personnelle.scolarite, trace=personnelle,
        valeurs={"commentaire": "Sami poursuit la suite après une relance de l’adulte."})
    associer(utilisateur=responsable, classe=classe, locale=groupe, ids=[eleves[5].pk], adoption_attendue=adoption.pk)
    ajouter_reussite(ids=[eleves[0].pk, eleves[4].pk], domaine_id=domaines["CORPS"],
        libelle="Je franchis le parcours en gardant mon équilibre", commentaire="Réussite observée pendant l’atelier fictif.", **commun)
