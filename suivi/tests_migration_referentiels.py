"""Validation sur des schémas historiques et une sauvegarde SQLite fictive."""
from datetime import date
import sqlite3
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


AVANT = ("suivi", "0015_competence_icone_formulationlocale_and_more")
FONDATIONS = ("suivi", "0016_fondations_referentiels_annuels")
APRES = ("suivi", "0017_cloture_et_ressources_referentiels")


class MigrationReferentiels(TransactionTestCase):
    def migrer(self, cible):
        executant = MigrationExecutor(connection)
        executant.migrate([cible])
        return executant.loader.project_state([cible]).apps

    def tearDown(self):
        self.migrer(("suivi", "0020_definitions_sources_ecoles"))
        super().tearDown()

    def test_ancienne_base_garde_identites_et_traces_masquees(self):
        apps = self.migrer(AVANT)
        ecole = apps.get_model("suivi", "Ecole").objects.create(nom="École de migration fictive")
        classe = apps.get_model("suivi", "Classe").objects.create(ecole=ecole, nom="Lucioles", annee_scolaire="2025-2026")
        domaine = apps.get_model("suivi", "Domaine").objects.create(ecole=ecole, code="LANG", nom="Langage")
        competence = apps.get_model("suivi", "Competence").objects.create(domaine=domaine, code="LANG-01", libelle="Je parle", active=False)
        eleve = apps.get_model("suivi", "Eleve").objects.create(ecole=ecole, prenom="Ana")
        scolarite = apps.get_model("suivi", "Scolarite").objects.create(eleve=eleve, classe=classe, annee_scolaire="2025-2026", niveau="PS")
        observation = apps.get_model("suivi", "Observation").objects.create(eleve=eleve, competence=competence, statut="en_cours", date_observation=date(2026, 6, 15))
        trace = apps.get_model("suivi", "Trace").objects.create(observation=observation, scolarite=scolarite, commentaire="Trace fictive", photo="traces/fictive.png")
        apps = self.migrer(APRES)
        reprise_observation = apps.get_model("suivi", "Observation").objects.get(pk=observation.pk)
        reprise_trace = apps.get_model("suivi", "Trace").objects.get(pk=trace.pk)
        self.assertEqual((reprise_observation.eleve_id, reprise_observation.competence_id, reprise_observation.statut),
                         (eleve.pk, competence.pk, "en_cours"))
        self.assertEqual(reprise_trace.commentaire, "Trace fictive")
        self.assertEqual(reprise_trace.photo.name, "traces/fictive.png")
        self.assertIsNone(reprise_trace.usage_referentiel_id)
        self.assertFalse(apps.get_model("suivi", "Competence").objects.get(pk=competence.pk).active)
        self.assertEqual(apps.get_model("suivi", "EtatAnnuelObservation").objects.count(), 0)

    def test_references_photo_initiale_migrees_sans_lire_stockage(self):
        apps = self.migrer(FONDATIONS)
        ecole = apps.get_model("suivi", "Ecole").objects.create(nom="École fictive reprise")
        source = apps.get_model("suivi", "SourceReferentiel").objects.create(identifiant="migration-fictive", titre="Initial", ecole=ecole)
        version = apps.get_model("suivi", "VersionReferentiel").objects.create(source=source, numero="initial", empreinte="a" * 64, contenu={})
        annuel = apps.get_model("suivi", "ReferentielAnnuel").objects.create(ecole=ecole, annee_scolaire="2025-2026", version_proposee=version,
            etat_initial={"reglages": [{"photo": "presentation/fictive.png"}, {"photo": ""}, {"photo": "presentation/fictive.png"}]})
        apps = self.migrer(APRES)
        references = apps.get_model("suivi", "RessourceReferentiel").objects.filter(annuel_id=annuel.pk)
        self.assertEqual(list(references.values_list("fichier", flat=True)), ["presentation/fictive.png"])

    @skipUnless(connection.vendor == "sqlite", "Vérification du paquet SQLite local uniquement.")
    def test_sauvegarde_sqlite_conserve_versions_annuelles_et_ressources(self):
        apps = self.migrer(APRES)
        ecole = apps.get_model("suivi", "Ecole").objects.create(nom="École sauvegardée fictive")
        source = apps.get_model("suivi", "SourceReferentiel").objects.create(identifiant="sauvegarde-fictive", titre="Initial", ecole=ecole)
        contenu = {"origine": "etat_initial_repris", "competences": [{"id": 1, "libelle": "Je parle"}]}
        version = apps.get_model("suivi", "VersionReferentiel").objects.create(source=source, numero="initial", empreinte="a" * 64, contenu=contenu)
        annuel = apps.get_model("suivi", "ReferentielAnnuel").objects.create(ecole=ecole, annee_scolaire="2025-2026", version_proposee=version, etat_initial={"reglages": []})
        apps.get_model("suivi", "RessourceReferentiel").objects.create(annuel=annuel, fichier="presentation/fictive.png")
        with TemporaryDirectory() as dossier:
            sauvegarde = sqlite3.connect(Path(dossier) / "carnet.sqlite3")
            try:
                connection.connection.backup(sauvegarde)
                self.assertEqual(sauvegarde.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(sauvegarde.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(sauvegarde.execute("SELECT COUNT(*) FROM suivi_versionreferentiel").fetchone()[0], 1)
                self.assertEqual(sauvegarde.execute("SELECT fichier FROM suivi_ressourcereferentiel").fetchone()[0], "presentation/fictive.png")
                restauration = sqlite3.connect(":memory:")
                try:
                    sauvegarde.backup(restauration)
                    self.assertEqual(restauration.execute("SELECT version_proposee_id FROM suivi_referentielannuel").fetchone()[0], version.pk)
                    self.assertEqual(restauration.execute("SELECT contenu FROM suivi_versionreferentiel").fetchone(),
                                     sauvegarde.execute("SELECT contenu FROM suivi_versionreferentiel").fetchone())
                finally:
                    restauration.close()
            finally:
                sauvegarde.close()
