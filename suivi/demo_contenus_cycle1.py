"""Contenus et situations fictives pour la démonstration, jamais pour la production."""
from datetime import date

import yaml
from django.conf import settings

from comptes.models import AffectationClasse, AppartenanceEcole
from suivi.models import Classe, Competence, Eleve, Observation, Scolarite
from suivi.referentiels import contenu_adoption
from suivi.services.adaptations_referentiels import enregistrer_adaptation
from suivi.services.adoption_bases_referentiels import adopter_base, apercu_adoption
from suivi.services.choix_bases_referentiels import publier_choix_application
from suivi.services.import_sources_referentiels import importer_source
from suivi.services.pedagogie import enregistrer_trace, modifier_etat
from suivi.services.contextes_referentiels import enregistrer_etat_annuel


def preparer_contenus_cycle1(ecole, utilisateurs, versions_fictives, revision_application):
    """Appelé seulement par la commande d'équipe avec confirmation fictive."""
    configuration = yaml.safe_load(
        (settings.BASE_DIR / "referentiel/DEMONSTRATION-CR5.yaml").read_text(encoding="utf-8")
    )
    annee = configuration["annee"]
    versions = {}
    for fichier in ("objectifs-programmes.yaml", "cycle1-etaye.yaml"):
        version, _, _ = importer_source(
            (settings.BASE_DIR / "referentiel/cycle1" / fichier).read_text(encoding="utf-8")
        )
        versions[version.source.identifiant] = version
    publier_choix_application(
        annee=annee, versions_ids=[v.pk for v in versions.values()] + versions_fictives,
        proposee_id=versions["petits-pas-cycle1-etaye"].pk,
        revision_attendue=revision_application,
    )
    for numero, specification in enumerate(configuration["classes"]):
        responsable = utilisateurs[specification["responsable"]]
        classe, _ = Classe.objects.get_or_create(
            ecole=ecole, nom=specification["nom"], annee_scolaire=annee,
            defaults={"ordre": specification["ordre"]},
        )
        appartenance = AppartenanceEcole.objects.get(ecole=ecole, utilisateur=responsable)
        affectation, _ = AffectationClasse.objects.get_or_create(
            appartenance=appartenance, classe=classe, type=AffectationClasse.RESPONSABLE,
            defaults={"date_debut": date(2026, 9, 1), "attribue_par": utilisateurs["diane"],
                      "motif": "Responsabilité fictive pour évaluer les contenus cycle 1"},
        )
        affectation.full_clean()
        classe.activer()
        version = versions[specification["source"]]
        apercu = apercu_adoption(utilisateur=responsable, classe=classe, version_id=version.pk)
        adoption = adopter_base(
            utilisateur=responsable, classe=classe, version_id=version.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
        )
        contenu = contenu_adoption(adoption)
        identites = {f"source-{d.identite_id}": d.identite.identifiant
                     for d in version.definitions.select_related("identite")}
        definitions = {identites[c["cle_definition"]]: c for c in contenu["competences"]}
        for indice, prenom in enumerate(configuration["prenoms"]):
            niveau = ("PS", "MS", "GS")[indice // 4]
            eleve = Eleve.objects.create(
                ecole=ecole, prenom=prenom, nom="Fictif" if numero == 0 else "Exemple",
                annee_naissance={"PS": 2023, "MS": 2022, "GS": 2021}[niveau],
            )
            scolarite = Scolarite(eleve=eleve, classe=classe, annee_scolaire=annee, niveau=niveau)
            scolarite.full_clean()
            scolarite.save()
            for j, situation in enumerate(configuration["situations"][niveau]):
                definition = definitions[situation["identite"]]
                competence = Competence.objects.get(pk=definition["id"])
                statut = (Observation.EN_COURS, Observation.REUSSI, Observation.NON_DEBUTE)[(indice + j) % 3]
                observation = modifier_etat(
                    utilisateur=responsable, eleve=eleve, competence=competence, statut=statut,
                )
                observation.date_observation = date(2026, 9, 21 + j)
                observation.save(update_fields=["date_observation"])
                usage = adoption.usages.get(competence=competence)
                enregistrer_etat_annuel(observation, usage)
                if statut != Observation.NON_DEBUTE:
                    enregistrer_trace(
                        utilisateur=responsable, eleve=eleve, competence=competence,
                        scolarite=scolarite, valeurs={
                            "date_observation": observation.date_observation,
                            "commentaire": situation["commentaire"], "visible_carnet": True,
                        },
                    )
        if specification["source"] == "petits-pas-cycle1-etaye":
            cible = definitions["r-soins-plantations"]
            enregistrer_adaptation(
                utilisateur=responsable, ecole=ecole, annee=annee, classe=classe,
                adoption_attendue=adoption.pk, competence=Competence.objects.get(pk=cible["id"]),
                libelle="Je participe aux soins des plantations de notre jardin de classe.",
                visible=None, revision_attendue=0,
            )
