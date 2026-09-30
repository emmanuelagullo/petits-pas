from datetime import date

from django.urls import reverse

from .models import AccesParcoursEleve, Classe, Competence, Scolarite, DemandeRapprochementEleve
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base


class CarnetsAnnuels(Base):
    def setUp(self):
        super().setUp()
        ancienne = Classe.objects.create(ecole=self.ecole, nom="Papillons", annee_scolaire="2025-2026")
        self.ancienne = Scolarite.objects.create(eleve=self.eleve, classe=ancienne,
                                                annee_scolaire=ancienne.annee_scolaire, niveau="PS")
        self.trace = self.creer_trace(scolarite=self.ancienne, commentaire="Trace de PS",
                                    date_observation=date(2026, 6, 12))
        reprendre(self.ecole.pk)
        demande = DemandeRapprochementEleve.objects.create(ecole=self.ecole, classe=self.classe,
            prenom_propose=self.eleve.prenom, niveau_propose="PS", demande_par=self.enseignant,
            etat="validee", eleve_retenu=self.eleve, decide_par=self.direction)
        AccesParcoursEleve.objects.create(demande=demande, eleve=self.eleve, classe=self.classe, valide_par=self.direction)
        self.entrer()

    def test_reussite_plus_recente_non_ajoutee_a_ancienne_annee(self):
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"annee": "2025-2026"})
        self.assertContains(page, "Trace de PS")
        self.assertContains(page, "État de cette année non retrouvé")
        self.assertEqual(page.context["scolarite"].pk, self.ancienne.pk)
        observations = [o for _d, groupes in page.context["domaines"] for _titre, lignes in groupes for _c, o in lignes if o]
        self.assertEqual(observations[0].statut, None)
        self.assertContains(page, "annee=2025-2026")
        self.assertEqual(self.client.get(reverse("carnet", args=[self.eleve.pk]),
            {"annee": "2025-2026", "contenu": "reussites"}).context["domaines"], [])

    def test_annee_non_autorisee_refusee(self):
        AccesParcoursEleve.objects.filter(eleve=self.eleve).delete()
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"annee": "2025-2026"})
        self.assertEqual(page.status_code, 404)
        self.assertEqual(self.client.get(reverse("carnet", args=[self.eleve.pk]), {"annee": "1999-2000"}).status_code, 404)

    def test_regroupement_annee_sans_date_non_invente(self):
        from django.utils import timezone
        self.trace.supprime_le = timezone.now()
        self.trace.save()
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]),
            {"annee": "2025-2026", "contenu": "tout", "regroupement": "bilan"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "état non retrouvé")
        self.assertNotContains(page, "Trace de PS")

    def test_progression_exclut_competence_masquee(self):
        from .views import _progression
        Competence.objects.filter(pk=self.competence.pk).update(active=False)
        eleves = [self.eleve]
        _progression(eleves, self.ecole, "tous", classe=self.classe)
        self.assertEqual(self.eleve.total_competences, 0)
        self.assertEqual(self.eleve.nb_reussies, 0)

    def test_pdf_reprend_annee_et_trace_autorisees(self):
        page = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]),
                               {"annee": "2025-2026", "contenu": "observes"})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page["Content-Type"], "application/pdf")
        self.assertTrue(page.content.startswith(b"%PDF"))
