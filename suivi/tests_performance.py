"""Budgets de requêtes sur des données fictives, sans seuil de temps fragile."""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .lectures_eleves import avec_scolarites_pour_lecture
from .models import Classe, Eleve, Scolarite
from .tests import Base


class ListesElevesPerformance(Base):
    def inscrire(self, nombre):
        for i in range(nombre):
            eleve = Eleve.objects.create(ecole=self.ecole, prenom=f"Fictif {i:02d}")
            Scolarite.objects.create(eleve=eleve, classe=self.classe,
                annee_scolaire=self.classe.annee_scolaire, niveau="MS")

    def test_scolarite_la_plus_recente_et_absence_sans_requetes(self):
        ancienne = Classe.objects.create(ecole=self.ecole, nom="Ancienne", annee_scolaire="2025-2026")
        Scolarite.objects.create(eleve=self.eleve, classe=ancienne, annee_scolaire=ancienne.annee_scolaire, niveau="GS")
        sans = Eleve.objects.create(ecole=self.ecole, prenom="Sans inscription")
        with self.assertNumQueries(2):
            eleves = list(avec_scolarites_pour_lecture(Eleve.objects.filter(pk__in=[self.eleve.pk, sans.pk])))
        with self.assertNumQueries(0):
            lou = next(e for e in eleves if e.pk == self.eleve.pk)
            self.assertEqual(lou.scolarite_courante().pk, self.scolarite.pk)
            self.assertEqual(lou.niveau, "PS")
            self.assertEqual(lou.classe.pk, self.classe.pk)
            self.assertIsNone(next(e for e in eleves if e.pk == sans.pk).scolarite_courante())
        # Le chemin ordinaire reste frais ; aucun cache implicite pour les écritures.
        Scolarite.objects.filter(pk=self.scolarite.pk).update(niveau="GS")
        self.assertEqual(Eleve.objects.get(pk=self.eleve.pk).niveau, "GS")

    def test_requetes_des_listes_independantes_de_effectif(self):
        self.client.force_login(self.enseignant)
        urls = [reverse("classe_detail", args=[self.classe.pk]),
                reverse("saisie_competence", args=[self.classe.pk, self.competence.pk]),
                reverse("preparer_edition", args=[self.classe.pk])]
        avant = []
        for url in urls:
            self.client.get(url)
            with CaptureQueriesContext(connection) as requetes:
                self.assertEqual(self.client.get(url).status_code, 200)
            avant.append(len(requetes))
        self.inscrire(29)
        for url, nombre in zip(urls, avant):
            with CaptureQueriesContext(connection) as requetes:
                page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertLessEqual(len(requetes), nombre)
            self.assertContains(page, "Fictif 28")

    def test_formulaire_trace_partagee_independant_de_effectif(self):
        self.client.force_login(self.enseignant)
        url = reverse("ajouter_trace_commune", args=[self.classe.pk, self.competence.pk])
        self.client.get(url)
        with CaptureQueriesContext(connection) as requetes:
            self.client.get(url)
        nombre = len(requetes)
        self.inscrire(29)
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url)
        self.assertLessEqual(len(requetes), nombre)
        self.assertContains(page, "Fictif 28")


class RegroupementCarnetPerformance(Base):
    def test_une_lecture_par_regroupement_et_pas_par_acquisition(self):
        from datetime import date
        from .models import Bilan, Observation
        from .views import _regrouper_lignes
        observation = Observation.objects.create(eleve=self.eleve, competence=self.competence,
            date_observation=date(2026, 10, 1))
        Bilan.objects.create(scolarite=self.scolarite, date_bilan=date(2026, 12, 1), texte="Bilan fictif")
        for mode, titre, budget in [("annuel", "Petite section — 2026-2027", 1),
                                     ("mensuel", "Octobre 2026", 0),
                                     ("bilan", "Mes acquisitions — décembre 2026", 1)]:
            with self.subTest(mode=mode), self.assertNumQueries(budget):
                groupes = _regrouper_lignes(self.eleve, [(self.competence, observation)] * 30, mode)
                self.assertEqual(groupes[0][0], titre)
                self.assertEqual(len(groupes[0][1]), 30)

    def test_budget_du_carnet_annuel_independant_des_acquisitions(self):
        from .models import Competence, Observation
        self.client.force_login(self.enseignant)
        Observation.objects.create(eleve=self.eleve, competence=self.competence)
        url = reverse("carnet", args=[self.eleve.pk])
        self.client.get(url, {"regroupement": "annuel"})
        with CaptureQueriesContext(connection) as requetes:
            self.client.get(url, {"regroupement": "annuel"})
        nombre = len(requetes)
        for i in range(30):
            competence = Competence.objects.create(domaine=self.competence.domaine, code=f"F{i}", libelle=f"Acquisition fictive {i}")
            Observation.objects.create(eleve=self.eleve, competence=competence)
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url, {"regroupement": "annuel"})
        self.assertLessEqual(len(requetes), nombre)
        self.assertContains(page, "Acquisition fictive 29")
