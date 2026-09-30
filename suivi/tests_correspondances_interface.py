from django.urls import reverse
from .models import CorrespondanceCompetence, Observation
from . import tests_correspondances_referentiels as fixtures
from .tests import Base


class InterfaceCorrespondances(Base):
    def setUp(self):
        super().setUp()
        from .services.reprise_referentiels import reprendre
        from .services.choix_bases_referentiels import publier_choix_application
        from .tests_import_sources_referentiels import document, importer
        from .services.correspondances_referentiels import catalogue_liens
        reprendre(self.ecole.pk)
        self.a = importer(document())[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()
        self.adopter(self.a)
        self.adoption = self.adopter(self.b)
        self.annee = self.classe.annee_scolaire
        self.catalogue = catalogue_liens(utilisateur=self.enseignant, ecole=self.ecole, annee=self.annee, classe=self.classe)
        self.ra = next(r for r, c in self.catalogue.items() if c["version_id"] == self.a.pk)
        self.rb = next(r for r, c in self.catalogue.items() if c["version_id"] == self.b.pk)
        self.url = reverse("correspondances_classe", args=[self.classe.pk])

    adopter = fixtures.Correspondances.adopter
    relier = fixtures.Correspondances.relier

    def donnees(self, page, **options):
        return {"action": "relier", "jeton": page.context["jeton"], "depart": self.rb, "arrivee": self.ra,
            "type_lien": "remplace", "justification": "Choix fictif de l'équipe.", "consequences": "on", **options}

    def test_consultation_sans_ecriture_validation_et_saisie(self):
        page = self.client.get(self.url)
        self.assertContains(page, "Valider ce lien")
        self.assertFalse(CorrespondanceCompetence.objects.exists())
        self.assertEqual(self.client.post(self.url, self.donnees(page)).status_code, 302)
        lien = CorrespondanceCompetence.objects.get()
        self.assertEqual(lien.auteur_id, self.enseignant.pk)
        self.assertFalse(Observation.objects.exists())
        self.assertContains(self.client.get(self.url), "Choix fictif de l&#x27;équipe.")
        page = self.client.get(reverse("saisie_competence", args=[self.classe.pk, lien.depart_id]))
        self.assertContains(page, "Correspondances entre apprentissages")
        self.assertContains(page, "Choix fictif de l&#x27;équipe.")
        page = self.client.post(reverse("referentiel_classe", args=[self.classe.pk]), {"action": "apercu", "version": self.a.pk})
        self.assertContains(page, "Choix fictif de l&#x27;équipe.")
        self.assertEqual(len(page.context["apercu"]["correspondances"]), 1)
        self.assertEqual(page.context["apercu"]["communes"], 0)

    def test_retrait_soft_et_formulaire_perime(self):
        lien = self.relier()
        page = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, {"action": "retirer", "jeton": page.context["jeton"],
            "lien": lien.pk, "revision": 0}).status_code, 302)
        lien.refresh_from_db()
        self.assertFalse(lien.active)
        page = self.client.post(self.url, self.donnees(page))
        self.assertEqual(page.status_code, 400)
        self.assertIsNone(page.context["jeton"])
        self.assertContains(page, "Reconsulter les correspondances", status_code=400)
        self.assertEqual(CorrespondanceCompetence.objects.count(), 1)

    def test_ecole_retrait_non_delegue_et_annee_signature(self):
        lien = self.relier(ecole=True)
        page = self.client.get(self.url)
        self.assertNotContains(page, "Retirer ce lien")
        self.assertEqual(self.client.post(self.url, {"action": "retirer", "jeton": page.context["jeton"],
            "lien": lien.pk, "revision": 0}).status_code, 403)
        self.assertEqual(self.client.get(reverse("correspondances_ecole")).status_code, 403)
        self.client.force_login(self.direction)
        url = reverse("correspondances_ecole") + "?annee=" + self.annee
        page = self.client.get(url)
        self.assertContains(page, "Retirer ce lien")
        autre = reverse("correspondances_ecole") + "?annee=2027-2028"
        self.assertEqual(self.client.post(autre, self.donnees(page)).status_code, 400)

    def test_cloture_conserve_et_refuse_post(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from .services.cloture_referentiels import clore
        self.relier()
        page = self.client.get(self.url)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            clore(utilisateur=self.enseignant, classe=self.classe)
        fermee = self.client.get(self.url)
        self.assertContains(fermee, "Rapprochement fictif")
        self.assertNotContains(fermee, "Valider ce lien")
        self.assertNotContains(fermee, "Retirer ce lien")
        self.assertEqual(self.client.post(self.url, self.donnees(page)).status_code, 400)

    def test_confirmation_consequences_self_cycle_et_base_changee(self):
        page = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.donnees(page, consequences="")).status_code, 400)
        self.assertEqual(self.client.post(self.url, self.donnees(page, arrivee=self.rb)).status_code, 400)
        self.assertFalse(CorrespondanceCompetence.objects.exists())
        self.relier(type_lien="remplace")
        page = self.client.get(self.url)
        self.assertEqual(self.client.post(self.url, self.donnees(page, depart=self.ra, arrivee=self.rb)).status_code, 400)
        self.adopter(self.a)
        refus = self.client.post(self.url, self.donnees(page))
        self.assertEqual(refus.status_code, 400)
        self.assertIsNone(refus.context["jeton"])

    def test_associe_consulte_sans_droit_de_validation(self):
        from django.contrib.auth import get_user_model
        from comptes.models import AffectationClasse, AppartenanceEcole
        self.relier()
        associe = get_user_model().objects.create_user(username="associe-correspondances-fictif")
        appartenance = AppartenanceEcole.objects.create(utilisateur=associe, ecole=self.ecole)
        AffectationClasse.objects.create(appartenance=appartenance, classe=self.classe,
                                        type=AffectationClasse.ENSEIGNANT_ASSOCIE)
        self.client.force_login(associe)
        page = self.client.get(self.url)
        self.assertContains(page, "Rapprochement fictif")
        self.assertNotContains(page, "Valider ce lien")
        self.assertNotContains(page, "Retirer ce lien")
        self.assertEqual(self.client.post(self.url, {"action": "relier"}).status_code, 403)
