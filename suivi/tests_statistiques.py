from datetime import date

from django.urls import reverse
from django.utils import timezone

from .models import Classe, Competence, Eleve, Observation, Scolarite
from .statistiques import repartition_competences
from .tests import Base


class RepartitionCompetences(Base):
    def inscrire(self, prenom, classe=None, archive=False):
        classe = classe or self.classe
        eleve = Eleve.objects.create(ecole=self.ecole, prenom=prenom,
                                    archive_le=timezone.now() if archive else None)
        Scolarite.objects.create(eleve=eleve, classe=classe,
                                annee_scolaire=classe.annee_scolaire, niveau="PS")
        return eleve

    def test_etats_actuels_classe_sans_archives_ni_autres_classes(self):
        en_cours = self.inscrire("Camille")
        self.inscrire("Sam")
        archive = self.inscrire("Alex", archive=True)
        autre_classe = Classe.objects.create(ecole=self.ecole, nom="Autre classe")
        autre = self.inscrire("Charlie", autre_classe)
        for eleve in [self.eleve, archive, autre]:
            Observation.objects.create(eleve=eleve, competence=self.competence,
                                       statut="reussi", date_observation=date(2020, 10, 1))
        Observation.objects.create(eleve=en_cours, competence=self.competence, statut="en_cours")
        self.assertEqual(repartition_competences(self.classe, [self.competence]), 3)
        self.assertEqual(self.competence.repartition["reussites"], 1)
        self.assertEqual(self.competence.repartition["en_cours"], 1)
        self.assertEqual(self.competence.repartition["non_observes"], 1)

    def test_deux_requetes_quel_que_soit_nombre_competences(self):
        with self.assertNumQueries(2):
            repartition_competences(self.classe, [self.competence])
        competences = [self.competence] + [Competence.objects.create(
            domaine=self.competence.domaine, code=f"C{i}", libelle=f"Compétence {i}") for i in range(20)]
        with self.assertNumQueries(2):
            repartition_competences(self.classe, competences)
        self.assertTrue(all(c.repartition["non_observes"] == 1 for c in competences))

    def test_classe_vide_et_statut_efface(self):
        Observation.objects.create(eleve=self.eleve, competence=self.competence, statut=None)
        repartition_competences(self.classe, [self.competence])
        self.assertEqual(self.competence.repartition["non_observes"], 1)
        self.eleve.archive_le = timezone.now()
        self.eleve.save()
        self.assertEqual(repartition_competences(self.classe, [self.competence]), 0)
        self.assertEqual(self.competence.repartition["reussites"], 0)

    def test_barre_accessible_et_actualisee_apres_saisie(self):
        self.client.force_login(self.enseignant)
        url = reverse("choisir_competence", args=[self.classe.pk])
        page = self.client.get(url)
        self.assertContains(page, 'class="repartition-observations"')
        self.assertContains(page, 'aria-label="0 réussites, 0 en cours, 1 non observée, sur 1 élève"')
        self.client.post(reverse("basculer", args=[self.eleve.pk, self.competence.pk]))
        self.assertContains(self.client.get(url), 'aria-label="1 réussite, 0 en cours, 0 non observées, sur 1 élève"')
