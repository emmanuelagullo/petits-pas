"""Préparation #R3a : lecture seule, sans déduction d'origine pédagogique."""
import json
import re
from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from suivi.models import (
    Attendu, Classe, Competence, Domaine, Ecole, FormulationLocale,
    FormulationProposee, Observation, ReglagePresentation, Scolarite,
    SousDomaine, Trace, TraceCommune,
)


class Command(BaseCommand):
    help = "Diagnostique les données avant la migration des référentiels, sans les modifier."

    def add_arguments(self, parser):
        parser.add_argument("--ecole", type=int, help="Limiter à une école par son identifiant.")
        parser.add_argument("--json", action="store_true", help="Rapport structuré, sans noms ni commentaires.")
        parser.add_argument("--exiger-coherent", action="store_true", help="Échouer si une incohérence bloquante est trouvée.")

    def handle(self, *args, **options):
        ecoles = Ecole.objects.order_by("pk")
        if options["ecole"] is not None:
            ecoles = ecoles.filter(pk=options["ecole"])
            if not ecoles.exists():
                raise CommandError("École introuvable.")
        rapports = [self.examiner(ecole) for ecole in ecoles.iterator()]
        rapport = {"format": 1, "lecture_seule": True, "ecoles": rapports,
                   "limites": ["Origines sources et anciennes présentations non déductibles.",
                               "Année des états courants à confirmer, même avec une date compatible.",
                               "Existence et contenu des médias non vérifiés.",
                               "Exécuter sur une copie restaurée pour un état stable."]}
        if options["json"]:
            self.stdout.write(json.dumps(rapport, ensure_ascii=False, indent=2))
        else:
            self.stdout.write("Diagnostic des référentiels — lecture seule")
            for ecole in rapports:
                self.stdout.write(f"École #{ecole['ecole_id']} — volumes : {ecole['volumes']}")
                for constat in ecole["constats"]:
                    self.stdout.write(f"[{constat['niveau']}] {constat['code']} : {constat['nombre']} — {constat['ids']}")
            for limite in rapport["limites"]:
                self.stdout.write(limite)
        if options["exiger_coherent"] and any(
            c["niveau"] == "bloquant" for e in rapports for c in e["constats"]
        ):
            raise CommandError("Incohérences bloquantes : consulter le rapport ; aucune correction effectuée.")

    def examiner(self, ecole):
        constats = []

        def noter(code, ids, niveau="bloquant"):
            ids = sorted(set(ids))
            if ids:
                constats.append({"code": code, "niveau": niveau, "nombre": len(ids), "ids": ids})

        competences = Competence.objects.filter(domaine__ecole=ecole)
        doublons = competences.values("domaine_id", "code").annotate(n=Count("pk")).filter(n__gt=1)
        ids_doublons = []
        for groupe in doublons:
            ids_doublons.extend(competences.filter(
                domaine_id=groupe["domaine_id"], code=groupe["code"]
            ).values_list("pk", flat=True))
        noter("codes_doublons_dans_domaine", ids_doublons)
        # La collision entre domaines est légale aujourd'hui, mais ambiguë pour
        # --desactiver-absents et pour une filiation déduite du code seul.
        collisions = competences.values("code").annotate(n=Count("domaine_id", distinct=True)).filter(n__gt=1)
        noter("codes_partages_entre_domaines", competences.filter(
            code__in=collisions.values("code")).values_list("pk", flat=True), "a_examiner")
        noter("competence_sous_domaine_incoherent", [c.pk for c in competences.select_related("sous_domaine")
              if c.sous_domaine_id and c.sous_domaine.domaine_id != c.domaine_id])
        observations = Observation.objects.filter(eleve__ecole=ecole).select_related("competence__domaine")
        noter("observation_autre_ecole", [o.pk for o in observations if o.competence.domaine.ecole_id != ecole.pk])
        noter("competence_masquee_avec_observations", competences.filter(active=False, observations__isnull=False)
              .values_list("pk", flat=True), "a_examiner")
        scolarites = list(Scolarite.objects.filter(eleve__ecole=ecole).select_related("classe"))
        noter("scolarite_ecole_ou_annee_incoherente", [s.pk for s in scolarites
              if s.classe.ecole_id != ecole.pk or s.annee_scolaire != s.classe.annee_scolaire])
        def annee_valide(valeur):
            return bool(re.fullmatch(r"[0-9]{4}-[0-9]{4}", valeur)) and int(valeur[5:]) == int(valeur[:4]) + 1

        noter("classe_annee_invalide", [c.pk for c in Classe.objects.filter(ecole=ecole)
              if not annee_valide(c.annee_scolaire)])
        noter("scolarite_annee_invalide", [s.pk for s in scolarites if not annee_valide(s.annee_scolaire)])
        annees = {}
        for s in scolarites:
            annees.setdefault(s.eleve_id, set()).add(s.annee_scolaire)
        noter("etat_sans_annee_unique", [o.pk for o in observations if len(annees.get(o.eleve_id, set())) != 1], "a_examiner")
        traces = Trace.objects.filter(observation__eleve__ecole=ecole).select_related(
            "observation", "scolarite__classe", "commune", "origine_commune")
        noter("trace_contexte_incoherent", [t.pk for t in traces if
              t.scolarite.eleve_id != t.observation.eleve_id or t.scolarite.classe.ecole_id != ecole.pk])
        noter("trace_origine_commune_incoherente", [t.pk for t in traces if
              (t.commune_id and t.origine_commune_id) or any(
                  source and (source.competence_id != t.observation.competence_id
                              or source.classe_id != t.scolarite.classe_id)
                  for source in (t.commune, t.origine_commune))])
        communes = TraceCommune.objects.filter(classe__ecole=ecole).select_related("competence__domaine")
        noter("trace_commune_autre_ecole", [t.pk for t in communes if t.competence.domaine.ecole_id != ecole.pk])
        for modele, code in ((ReglagePresentation, "reglage_presentation_incoherent"),
                             (FormulationLocale, "formulation_locale_incoherente")):
            invalides = []
            for objet in modele.objects.filter(ecole=ecole).select_related("classe", "competence__domaine"):
                try:
                    objet.clean()
                except ValidationError:
                    invalides.append(objet.pk)
            noter(code, invalides)
        noter("competence_sans_origine_versionnee", competences.values_list("pk", flat=True), "information")
        volumes = {"domaines": Domaine.objects.filter(ecole=ecole).count(),
                   "competences": competences.count(), "observations": observations.count(),
                   "traces": traces.count(), "traces_communes": communes.count(),
                   "classes": Classe.objects.filter(ecole=ecole).count(),
                   "scolarites": len(scolarites),
                   "formulations_fournies": FormulationProposee.objects.filter(competence__domaine__ecole=ecole).count(),
                   "sous_domaines": SousDomaine.objects.filter(domaine__ecole=ecole).count(),
                   "attendus": Attendu.objects.filter(domaine__ecole=ecole).count()}
        return {"ecole_id": ecole.pk, "annees": dict(sorted(Counter(s.annee_scolaire for s in scolarites).items())),
                "volumes": volumes, "constats": constats}
