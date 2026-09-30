from django.urls import reverse
from django.core import signing
from .models import CompetenceLocale, DisponibiliteCompetenceLocale, Observation
from . import tests_ajouts_referentiels as fixtures
from .tests import Base


class InterfaceAjouts(Base):
    def setUp(self):
        super().setUp()
        from .services.reprise_referentiels import reprendre
        from .services.choix_bases_referentiels import publier_choix_application
        from .tests_import_sources_referentiels import document, importer
        reprendre(self.ecole.pk)
        self.a = importer(document())[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    adopter = fixtures.AjoutsLocaux.adopter
    creer = fixtures.AjoutsLocaux.creer

    def page(self, classe=True, locale=None):
        if classe:
            return reverse("ajout_classe", args=[self.classe.pk, locale.pk]) if locale else reverse("ajouts_classe", args=[self.classe.pk])
        return (reverse("ajout_ecole", args=[locale.pk]) if locale else reverse("ajouts_ecole")) + "?annee=" + self.classe.annee_scolaire

    def test_creation_get_sans_ecriture_et_saisie_carnet(self):
        adoption = self.adopter()
        url = self.page()
        page = self.client.get(url)
        self.assertContains(page, "Créer la compétence")
        self.assertFalse(CompetenceLocale.objects.exists())
        self.assertEqual(self.client.post(url, {"jeton": page.context["jeton"], "action": "creer",
            "libelle": "Je range des objets fictifs", "niveau": "PS", "domaine": adoption.contenu["domaines"][0]["id"]}).status_code, 302)
        locale = CompetenceLocale.objects.get()
        page = self.client.get(reverse("saisie_competence", args=[self.classe.pk, locale.competence_id]))
        self.assertContains(page, "Je range des objets fictifs")
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Je range des objets fictifs")
        self.assertFalse(Observation.objects.exists())

    def test_reprise_et_direction_propose_sans_push(self):
        locale = self.creer()
        self.client.force_login(self.direction)
        page = self.client.get(self.page(False))
        avant = DisponibiliteCompetenceLocale.objects.count()
        self.assertEqual(self.client.post(self.page(False), {"jeton": page.context["jeton"],
            "action": "proposer", "locale": locale.pk}).status_code, 302)
        self.assertEqual(DisponibiliteCompetenceLocale.objects.count(), avant + 1)
        self.assertEqual(locale.disponibilites.filter(classe__isnull=False).count(), 1)
        self.assertEqual(locale.classe_origine_id, self.classe.pk)
        self.assertFalse(Observation.objects.exists())

    def test_adaptation_masquage_et_demasquage(self):
        locale = self.creer()
        url = self.page(locale=locale)
        page = self.client.get(url)
        self.assertContains(page, "Origine de cet ajout")
        donnees = {"jeton": page.context["jeton"], "action": "adapter", "mode_libelle": "personnel",
            "libelle": "Je classe des objets fictifs", "meme_sens": "on", "visibilite": "masquer"}
        self.assertEqual(self.client.post(url, donnees).status_code, 302)
        self.assertContains(self.client.get(self.page()), "Je classe des objets fictifs")
        self.assertEqual(self.client.post(url, donnees).status_code, 400)
        page = self.client.get(url)
        self.assertEqual(self.client.post(url, {"jeton": page.context["jeton"], "action": "adapter",
            "libelle": "Je classe des objets fictifs", "meme_sens": "on", "visibilite": "montrer"}).status_code, 302)

    def test_compte_annee_et_base_lies_au_formulaire(self):
        self.adopter()
        page = self.client.get(self.page())
        self.adopter(self.b)
        self.assertEqual(self.client.post(self.page(), {"jeton": page.context["jeton"], "action": "creer"}).status_code, 400)
        self.assertFalse(CompetenceLocale.objects.exists())
        self.client.force_login(self.direction)
        page = self.client.get(self.page(False))
        autre = reverse("ajouts_ecole") + "?annee=2027-2028"
        self.assertEqual(self.client.post(autre, {"jeton": page.context["jeton"], "action": "creer"}).status_code, 400)
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(self.page(False)).status_code, 403)

    def test_jeton_expire_ne_fournit_pas_de_nouvelle_autorisation(self):
        self.adopter()
        page = self.client.post(self.page(), {"action": "creer", "jeton": "incorrect"})
        self.assertEqual(page.status_code, 400)
        self.assertIsNone(page.context["jeton"])
        self.assertContains(page, "Reconsulter les ajouts", status_code=400)

    def test_heritage_ecole_et_cloture_restent_independants(self):
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from .services.adaptations_referentiels import enregistrer_adaptation
        from .services.cloture_referentiels import clore
        locale = self.creer(classe=False)
        page = self.client.get(self.page())
        self.client.post(self.page(), {"jeton": page.context["jeton"], "action": "reprendre", "locale": locale.pk})
        enregistrer_adaptation(utilisateur=self.direction, ecole=self.ecole,
            annee=self.classe.annee_scolaire, competence=locale.competence, libelle="Je classe seul des objets fictifs",
            visible=True, meme_sens=True, revision_attendue=0)
        self.assertContains(self.client.get(self.page()), "Je classe seul des objets fictifs")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            clore(utilisateur=self.enseignant, classe=self.classe)
        enregistrer_adaptation(utilisateur=self.direction, ecole=self.ecole,
            annee=self.classe.annee_scolaire, competence=locale.competence, libelle="Je range mes objets fictifs",
            visible=False, meme_sens=True, revision_attendue=1)
        page = self.client.get(self.page())
        self.assertContains(page, "Je classe seul des objets fictifs")
        self.assertNotContains(page, "Je range mes objets fictifs")
        self.assertNotContains(page, "Créer la compétence")
        self.assertNotContains(self.client.get(self.page(locale=locale)), "Enregistrer les choix")

    def test_libelle_origine_et_proposition_ecole_sont_distingues(self):
        from .services.adaptations_referentiels import enregistrer_adaptation
        locale = self.creer()
        url = self.page(locale=locale)
        page = self.client.get(url)
        self.assertContains(page, "Libellé de la compétence")
        self.assertNotContains(page, 'name="mode_libelle"')
        self.assertNotContains(page, "data-libelle-personnel")
        self.assertNotContains(page, "Libellé proposé par l’école")
        self.assertEqual(page.context["form"]["libelle"].value(), locale.competence.libelle)
        enregistrer_adaptation(utilisateur=self.direction, ecole=self.ecole,
            annee=self.classe.annee_scolaire, competence=locale.competence,
            libelle="Je classe des objets fictifs", visible=None, meme_sens=True, revision_attendue=0)
        page = self.client.get(url)
        self.assertContains(page, "Suivre le libellé de l’école")
        self.assertContains(page, "Libellé proposé par l’école")
        self.assertEqual(page.context["form"]["libelle"].value(), "Je classe des objets fictifs")

    def test_libelle_direct_exige_confirmation_et_conserve_origine(self):
        locale = self.creer()
        definition = locale.definition
        competence_id = locale.competence_id
        url = self.page(locale=locale)
        page = self.client.get(url)
        donnees = {"jeton": page.context["jeton"], "action": "adapter", "mode_libelle": "garder",
            "libelle": "Je trie des objets fictifs", "visibilite": "montrer"}
        self.assertEqual(self.client.post(url, donnees).status_code, 400)
        donnees["meme_sens"] = "on"
        self.assertEqual(self.client.post(url, donnees).status_code, 302)
        locale.refresh_from_db()
        self.assertEqual(locale.definition, definition)
        self.assertEqual(locale.competence_id, competence_id)
        self.assertContains(self.client.get(self.page()), "Je trie des objets fictifs")
        self.assertEqual(self.client.get(url).context["form"]["libelle"].value(), "Je trie des objets fictifs")

    def test_ajout_ecole_repris_garde_choix_de_libelle(self):
        locale = self.creer(classe=False)
        page = self.client.get(self.page())
        self.assertEqual(self.client.post(self.page(), {"jeton": page.context["jeton"],
            "action": "reprendre", "locale": locale.pk}).status_code, 302)
        page = self.client.get(self.page(locale=locale))
        self.assertContains(page, "Garder le libellé d’origine")
        self.assertContains(page, 'name="mode_libelle"')
