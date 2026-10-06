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


class TracesSansPhotoPerformance(Base):
    def test_liste_sans_photos_ne_multiplie_pas_les_controles_de_medias(self):
        from .models import Observation, Trace
        observation = Observation.objects.create(eleve=self.eleve, competence=self.competence)
        Trace.objects.create(observation=observation, scolarite=self.scolarite, commentaire="Trace fictive")
        self.client.force_login(self.enseignant)
        url = reverse("trace", args=[self.eleve.pk, self.competence.pk])
        self.client.get(url)
        with CaptureQueriesContext(connection) as requetes:
            self.client.get(url)
        nombre = len(requetes)
        Trace.objects.bulk_create([Trace(observation=observation, scolarite=self.scolarite,
            commentaire=f"Texte fictif {i}") for i in range(30)])
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url)
        self.assertLessEqual(len(requetes), nombre)
        self.assertContains(page, "Texte fictif 29")
        self.assertNotContains(page, "Télécharger la photo enregistrée")


class EquipePerformance(Base):
    def ajouter_responsables(self, debut, fin):
        from django.contrib.auth import get_user_model
        from comptes.models import AffectationClasse, AppartenanceEcole
        for i in range(debut, fin):
            membre = AppartenanceEcole.objects.create(ecole=self.ecole,
                utilisateur=get_user_model().objects.create_user(username=f"equipe-fictive-{i}"))
            classe = Classe.objects.create(ecole=self.ecole, nom=f"Classe fictive {i}")
            AffectationClasse.objects.create(appartenance=membre, classe=classe, type="responsable")
            classe.activer()

    def test_croissance_lineaire_des_requetes_de_replacement(self):
        self.client.force_login(self.direction)
        url = reverse("equipe_ecole")
        self.ajouter_responsables(0, 5)
        self.client.get(url)
        with CaptureQueriesContext(connection) as requetes:
            self.client.get(url)
        nombre = len(requetes)
        self.ajouter_responsables(5, 30)
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url)
        # Les contrôles de fin d'affectation restent individuels ; seule la
        # recherche des remplaçants cesse de multiplier les allers-retours.
        self.assertLessEqual(len(requetes), nombre + 8 * 25)
        self.assertContains(page, "equipe-fictive-29")

    def test_remplacants_conservent_les_limites_de_dates_et_etats(self):
        from datetime import timedelta
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from comptes.models import AffectationClasse, AppartenanceEcole
        aujourd_hui = timezone.localdate()
        candidats = {}
        for nom, debut, fin, etat in [
            ("future", aujourd_hui + timedelta(days=1), None, "active"),
            ("finie", aujourd_hui - timedelta(days=2), aujourd_hui - timedelta(days=1), "active"),
            ("fin-aujourdhui", aujourd_hui - timedelta(days=1), aujourd_hui, "active"),
            ("suspendue", aujourd_hui, None, "suspendue"),
        ]:
            membre = AppartenanceEcole.objects.create(ecole=self.ecole,
                utilisateur=get_user_model().objects.create_user(username=nom))
            candidats[nom] = membre.pk
            AffectationClasse.objects.create(appartenance=membre, classe=self.classe,
                type="contributeur", date_debut=debut, date_fin=fin, etat=etat)
        self.client.force_login(self.direction)
        page = self.client.get(reverse("equipe_ecole"))
        responsable = next(a for m in page.context['appartenances']
            if m.pk == self.appartenance_enseignant.pk for a in m.affectations_classes.all())
        remplacants = {m.pk for m in responsable.remplacants}
        self.assertTrue({candidats['future'], candidats['finie'], candidats['suspendue']} <= remplacants)
        self.assertNotIn(candidats['fin-aujourdhui'], remplacants)
        self.assertNotIn(self.appartenance_enseignant.pk, remplacants)


class TracesAvecPhotoPerformance(Base):
    def test_relations_des_traces_chargees_ensemble_sans_eluder_les_droits(self):
        from .models import Observation, Trace
        observation = Observation.objects.create(eleve=self.eleve, competence=self.competence)
        Trace.objects.create(observation=observation, scolarite=self.scolarite, photo="photo-fictive.png")
        self.client.force_login(self.enseignant)
        url = reverse("trace", args=[self.eleve.pk, self.competence.pk])
        self.client.get(url)
        def lectures_classe(requetes):
            return sum(q['sql'].startswith('SELECT "suivi_classe".') for q in requetes)
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url)
        nombre = lectures_classe(requetes)
        self.assertContains(page, "Télécharger la photo enregistrée")
        Trace.objects.bulk_create([Trace(observation=observation, scolarite=self.scolarite,
            photo="photo-fictive.png") for _ in range(20)])
        with CaptureQueriesContext(connection) as requetes:
            page = self.client.get(url)
        self.assertLessEqual(lectures_classe(requetes), nombre)
        self.assertContains(page, "Télécharger la photo enregistrée", count=21)


class EnregistrementPartagePerformance(Base):
    def test_cout_par_enfant_limite_aux_attributions(self):
        from .models import Observation
        from .services.traces_communes import enregistrer_commune
        eleves = [self.eleve]
        for i in range(29):
            eleve = Eleve.objects.create(ecole=self.ecole, prenom=f"Fictif {i}")
            Scolarite.objects.create(eleve=eleve, classe=self.classe,
                annee_scolaire=self.classe.annee_scolaire, niveau="PS")
            eleves.append(eleve)
        Observation.objects.bulk_create([Observation(eleve=e, competence=self.competence, statut="reussi") for e in eleves])
        mesures = []
        for nombre in [5, 30]:
            with CaptureQueriesContext(connection) as requetes:
                commune = enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
                    competence=self.competence, ids=[e.pk for e in eleves[:nombre]],
                    valeurs={"commentaire":"<prénom> essaie une activité fictive."})
            mesures.append(len(requetes))
            self.assertEqual(commune.attributions.count(), nombre)
            self.assertTrue(commune.attributions.filter(commentaire="Lou essaie une activité fictive.").exists())
        self.assertLessEqual(mesures[1], mesures[0] + 4 * 25)
        self.assertEqual(set(Observation.objects.values_list("statut", flat=True)), {"reussi"})

    def test_selection_hors_classe_refusee_avant_ecriture(self):
        from django.core.exceptions import ValidationError
        from .models import TraceCommune
        from .services.traces_communes import enregistrer_commune
        autre = Eleve.objects.create(ecole=self.ecole, prenom="Autre classe fictive")
        with self.assertRaises(ValidationError):
            enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
                competence=self.competence, ids=[self.eleve.pk, autre.pk],
                valeurs={"commentaire":"Texte fictif"})
        self.assertFalse(TraceCommune.objects.exists())
