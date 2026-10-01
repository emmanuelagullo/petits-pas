from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import SimpleTestCase
from .consultation_referentiels import rechercher_apprentissages
from .tests import Base
from .models import AdoptionReferentiel, Competence, UsageCompetence, VersionSourceEcole
from .tests_import_sources_referentiels import document, importer
from .services.reprise_referentiels import reprendre
from .services.choix_bases_referentiels import publier_choix_application


class ConsultationReferentiels(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.version = importer(document())[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.version.pk],
                                 proposee_id=self.version.pk, revision_attendue=0)
        self.entrer()
        self.url = reverse("consulter_referentiels_classe", args=[self.classe.pk])

    def test_catalogue_source_sans_projection_ni_adoption(self):
        avant = [m.objects.count() for m in (AdoptionReferentiel, Competence, UsageCompetence, VersionSourceEcole)]
        page = self.client.get(self.url, {"version": self.version.pk})
        self.assertContains(page, "Je parle")
        self.assertContains(page, self.version.source.licence)
        self.assertContains(page, "Lecture seule")
        self.assertEqual(page.context["total"], 1)
        self.assertEqual(avant, [m.objects.count() for m in (AdoptionReferentiel, Competence, UsageCompetence, VersionSourceEcole)])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_recherche_sections_et_refus_version_etrangere(self):
        self.assertEqual(self.client.get(self.url, {"version": self.version.pk, "q": "PARLE"}).context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(self.url, {"version": self.version.pk, "q": "parlf"}).context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(self.url, {"version": self.version.pk, "niveau": "GS"}).context["page"].paginator.count, 0)
        hors = importer(document("hors-choix-fictif"))[0]
        self.assertEqual(self.client.get(self.url, {"version": hors.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"version": self.version.pk, "lecture": "classe"}).status_code, 404)

    def test_catalogue_local_complet_malgre_filtres_sans_donnees_de_suivi(self):
        page = self.client.get(self.url, {"version": self.version.pk, "q": "introuvable"})
        self.assertEqual(page.context["page"].paginator.count, 0)
        self.assertEqual(len(page.context["catalogue"]), 1)
        self.assertEqual(set(page.context["catalogue"][0]),
                         {"libelle", "domaine", "groupe", "niveau", "code", "active"})
        self.assertContains(page, 'id="catalogue-referentiel"')
        self.assertContains(page, 'data-recherche-referentiel')

    def test_associe_consulte_sans_droit_de_changer(self):
        from comptes.models import AffectationClasse
        # Modifier l'affectation fictive existante ; ne pas créer un rôle supplémentaire.
        from comptes.models import AppartenanceEcole
        appartenance = AppartenanceEcole.objects.get(utilisateur=self.enseignant, ecole=self.ecole)
        AffectationClasse.objects.filter(appartenance=appartenance, classe=self.classe).update(type=AffectationClasse.ENSEIGNANT_ASSOCIE)
        self.assertEqual(self.client.get(self.url, {"version": self.version.pk}).status_code, 200)
        self.assertEqual(self.client.get(reverse("referentiel_classe", args=[self.classe.pk])).status_code, 404)
        sans = get_user_model().objects.create_user(username="sans-droit-fictif")
        self.client.force_login(sans)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_page_courante_regroupe_changement_dans_avance(self):
        page = self.client.get(reverse("referentiel_classe", args=[self.classe.pk]))
        self.assertContains(page, 'class="operations-avancees"')
        self.assertNotContains(page, 'class="operations-avancees" open')
        self.assertContains(page, "Consulter les référentiels")
        self.assertContains(page, "Libellés et compétences masquées")


class RechercheApprentissages(SimpleTestCase):
    def test_accents_ordre_des_mots_et_faute(self):
        lignes = [{"libelle": "Je reconnais mon prénom"}, {"libelle": "Je découpe du papier"}]
        self.assertEqual(rechercher_apprentissages(lignes, "prenom reconnais"), lignes[:1])
        self.assertEqual(rechercher_apprentissages(lignes, "reconnais prenom"), lignes[:1])
        self.assertEqual(rechercher_apprentissages(lignes, "reconnais prenomx"), lignes[:1])
        self.assertEqual(rechercher_apprentissages(lignes, "prneom"), lignes[:1])
        self.assertEqual(rechercher_apprentissages(lignes, "prenom papier"), [])
        self.assertEqual(rechercher_apprentissages(lignes, "xyz"), [])

    def test_exact_avant_proche_et_ordre_stable(self):
        lignes = [{"libelle": "Je classe"}, {"libelle": "Je chasse"}, {"libelle": "Je chasse des images"}]
        self.assertEqual(rechercher_apprentissages(lignes, "chasse"), lignes[1:] + lignes[:1])
        self.assertEqual(rechercher_apprentissages(lignes, ""), lignes)


class LiensDocumentaires(SimpleTestCase):
    def test_liens_seulement_pour_references_declarees(self):
        from types import SimpleNamespace
        from .consultation_referentiels import liens_documentaires
        source = SimpleNamespace(provenance="BO n°41 du 31 octobre 2024", licence="CC-BY-SA-4.0")
        liens = liens_documentaires(source)
        self.assertEqual(len(liens["documents"]), 1)
        self.assertIn("MENE2415135A", liens["documents"][0][1])
        self.assertEqual(len(liens["licences"]), 1)
        self.assertEqual(liens_documentaires(SimpleNamespace(provenance="Source fictive inconnue", licence="Autre mention")), {"documents": [], "licences": []})
