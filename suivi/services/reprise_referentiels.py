"""Reprise explicite d'une copie de base existante, sans origine supposée."""
import hashlib
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

from suivi.models import (
    AdoptionReferentiel, Attendu, Classe, Competence, Domaine, Ecole,
    EtatAnnuelObservation, FormulationLocale, FormulationProposee,
    ReferentielAnnuel, ReglagePresentation, Scolarite, SousDomaine,
    SourceReferentiel, Trace, TraceCommune, UsageCompetence, VersionReferentiel, RessourceReferentiel,
)


def lignes(queryset, *champs):
    return list(queryset.order_by("pk").values(*champs))


@transaction.atomic
def reprendre(ecole_id):
    # Verrou de coordination entre deux appels de reprise sur PostgreSQL.
    ecole = Ecole.objects.select_for_update().get(pk=ecole_id)
    identifiant = f"reprise-ecole-{ecole.pk}"
    precedente = SourceReferentiel.objects.filter(identifiant=identifiant).first()
    if precedente:
        if precedente.ecole_id != ecole.pk or not precedente.versions.filter(numero="initial").exists():
            raise CommandError("Identifiant de reprise déjà utilisé sans état initial complet.")
        return False
    if ReferentielAnnuel.objects.filter(ecole=ecole).exists():
        raise CommandError("Choix annuels déjà présents : reprise automatique refusée.")
    sortie = StringIO()
    call_command("diagnostiquer_referentiels", ecole=ecole.pk, json=True,
                 exiger_coherent=True, stdout=sortie)
    competences = Competence.objects.filter(domaine__ecole=ecole)
    contenu = {
        "format": 1, "origine": "etat_initial_repris",
        "domaines": lignes(Domaine.objects.filter(ecole=ecole), "id", "code", "nom", "ordre"),
        "sous_domaines": lignes(SousDomaine.objects.filter(domaine__ecole=ecole), "id", "domaine_id", "code", "nom", "ordre"),
        "attendus": lignes(Attendu.objects.filter(domaine__ecole=ecole), "id", "domaine_id", "code", "texte", "ordre"),
        "competences": lignes(competences, "id", "domaine_id", "sous_domaine_id", "code", "libelle", "niveau", "ordre", "active", "icone"),
        "formulations": lignes(FormulationProposee.objects.filter(competence__domaine__ecole=ecole), "id", "competence_id", "code", "texte", "ordre", "active"),
    }
    empreinte = hashlib.sha256(json.dumps(contenu, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    source = SourceReferentiel.objects.create(identifiant=identifiant, titre="État initial repris",
                                             provenance="Base existante ; origine source non établie", ecole=ecole)
    version = VersionReferentiel.objects.create(source=source, numero="initial", empreinte=empreinte, contenu=contenu)
    reglages = lignes(ReglagePresentation.objects.filter(ecole=ecole), "id", "classe_id", "competence_id", "mode", "icone", "photo")
    formulations = lignes(FormulationLocale.objects.filter(ecole=ecole), "id", "classe_id", "competence_id", "origine_id", "origine_locale_id", "mode", "texte")
    classes = list(Classe.objects.filter(ecole=ecole).order_by("pk"))
    annuels = {}
    usages = {}
    for classe in classes:
        if classe.annee_scolaire not in annuels:
            annuels[classe.annee_scolaire] = ReferentielAnnuel.objects.create(
                ecole=ecole, annee_scolaire=classe.annee_scolaire, version_proposee=version,
                origine_reprise=True, historique_reconstitue=False,
                etat_initial={"reglages": reglages, "formulations_locales": formulations,
                              "avertissement": "Réglages présents à la reprise, pas une présentation historique reconstituée."})
        for reglage in reglages:
            if reglage["photo"]:
                RessourceReferentiel.objects.get_or_create(annuel=annuels[classe.annee_scolaire], fichier=reglage["photo"])
        adoption = AdoptionReferentiel.objects.create(classe=classe, annuel=annuels[classe.annee_scolaire],
                                                      version=version, reprise=True)
        for competence in competences:
            usage = UsageCompetence.objects.create(adoption=adoption, competence=competence,
                                                    cle_definition=f"locale-{competence.pk}")
            usages[(classe.pk, competence.pk)] = usage
    for trace in Trace.objects.filter(observation__eleve__ecole=ecole).select_related("observation", "scolarite"):
        trace.usage_referentiel = usages[(trace.scolarite.classe_id, trace.observation.competence_id)]
        trace.save(update_fields=["usage_referentiel"])
    for commune in TraceCommune.objects.filter(classe__ecole=ecole):
        commune.usage_referentiel = usages[(commune.classe_id, commune.competence_id)]
        commune.save(update_fields=["usage_referentiel"])
    # Aucun état courant n'est antidaté. Les années de scolarité sont connues,
    # leurs états finaux ne le sont pas, même avec une seule scolarité.
    for scolarite in Scolarite.objects.filter(eleve__ecole=ecole).select_related("eleve"):
        for observation in scolarite.eleve.observations.all():
            EtatAnnuelObservation.objects.create(observation=observation,
                annee_scolaire=scolarite.annee_scolaire,
                usage=usages[(scolarite.classe_id, observation.competence_id)], connu=False)
    return True


@transaction.atomic
def preparer_nouvelle_ecole(ecole):
    """Appelé immédiatement après le chargement de la trame de démarrage."""
    if reprendre(ecole.pk):
        source = SourceReferentiel.objects.get(identifiant=f"reprise-ecole-{ecole.pk}")
        source.titre = "Trame de travail fournie par Petits Pas"
        source.provenance = "Trame provisoire chargée à l'installation depuis referentiel/trame-cycle1.yaml"
        source.save(update_fields=["titre", "provenance"])
