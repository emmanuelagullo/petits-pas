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
