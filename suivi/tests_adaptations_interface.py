from tempfile import TemporaryDirectory

from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from .models import AdaptationCompetence, AdoptionReferentiel, Observation, Trace
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.cloture_referentiels import clore
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base


class AdaptationsInterface(Base):
    def setUp(self):
        super().setUp()
        self.creer_trace(commentaire="Parcours fictif conservé")
        reprendre(self.ecole.pk)
        self.adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        self.version = self.adoption.version
        self.annee = self.classe.annee_scolaire
        self.entrer()
        self.url = reverse("adaptation_competence_classe", args=[self.classe.pk, self.competence.pk])
        self.parametres = {"version": self.version.pk, "annee": self.annee}

    def page(self):
        return self.client.get(self.url, self.parametres)

    def enregistrer(self, page=None, **options):
        page = page or self.page()
        valeurs = {**self.parametres, "jeton": page.context["jeton"], "mode_libelle": "garder", "visibilite": "garder"}
        valeurs.update(options)
        return self.client.post(self.url, valeurs)

    def test_index_inclut_masquees_et_origine_sans_ecriture(self):
        page = self.client.get(reverse("adaptations_classe", args=[self.classe.pk]))
        self.assertContains(page, "Je dis mon prénom")
        self.assertContains(self.page(), "Libellé fourni")
        self.assertFalse(AdaptationCompetence.objects.exists())
        self.enregistrer(visibilite="masquer")
        page = self.client.get(reverse("adaptations_classe", args=[self.classe.pk]))
        self.assertContains(page, "Je dis mon prénom")
        self.assertContains(page, "masquée")
        self.assertContains(self.client.get(reverse("referentiel_classe", args=[self.classe.pk])), "Libellés et compétences masquées")

    def test_libelle_fidele_affiche_partout_sans_recrire_observations(self):
        self.assertNotContains(self.page(), 'name="meme_sens"')
        avant = list(Observation.objects.values()), list(Trace.objects.values())
        page = self.enregistrer(mode_libelle="personnel", libelle="Je me présente")
        self.assertEqual(page.status_code, 302)
        self.assertEqual((list(Observation.objects.values()), list(Trace.objects.values())), avant)
        urls = (reverse("choisir_competence", args=[self.classe.pk]),
                reverse("saisie_competence", args=[self.classe.pk, self.competence.pk]),
                reverse("trace", args=[self.eleve.pk, self.competence.pk]),
                reverse("traces_communes", args=[self.classe.pk, self.competence.pk]),
                reverse("carnet", args=[self.eleve.pk]))
        for url in urls:
            with self.subTest(url=url): self.assertContains(self.client.get(url), "Je me présente")
        self.assertContains(self.page(), "Je dis mon prénom")
        self.competence.refresh_from_db()
        self.assertEqual(self.competence.libelle, "Je dis mon prénom")
        self.assertEqual(self.enregistrer().status_code, 302)
        self.assertContains(self.client.get(reverse("choisir_competence", args=[self.classe.pk])), "Je dis mon prénom")

    def test_masquer_et_demasquer_sans_perdre_parcours(self):
        self.enregistrer(visibilite="masquer")
        self.assertNotContains(self.client.get(reverse("choisir_competence", args=[self.classe.pk])), "Je dis mon prénom")
        self.assertContains(self.client.get(reverse("carnet", args=[self.eleve.pk])), "Parcours fictif conservé")
        trace = self.client.get(reverse("trace", args=[self.eleve.pk, self.competence.pk]))
        self.assertContains(trace, "n’est pas disponible pour une nouvelle saisie")
        self.assertNotContains(trace, "Ajouter la trace")
        grille = self.client.get(reverse("saisie_competence", args=[self.classe.pk, self.competence.pk]))
        self.assertFalse(grille.context["responsable"])
        self.assertNotContains(self.client.get(reverse("traces_communes", args=[self.classe.pk, self.competence.pk])), "Ajouter une trace commune")
        with self.assertRaises(PermissionDenied):
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        self.enregistrer(visibilite="montrer")
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        self.assertEqual(Observation.objects.get().statut, "reussi")

    def test_libelle_vide_et_formulaire_perime(self):
        for options in ({"mode_libelle": "personnel", "libelle": " "},
                        {"visibilite": "autre"}):
            with self.subTest(options=options): self.assertEqual(self.enregistrer(**options).status_code, 400)
        self.assertFalse(AdaptationCompetence.objects.exists())
        ancienne = self.page()
        self.enregistrer(visibilite="masquer")
        refusee = self.enregistrer(ancienne, visibilite="montrer")
        self.assertEqual(refusee.status_code, 400)
        self.assertIsNone(refusee.context["jeton"])
        self.assertFalse(AdaptationCompetence.objects.get().visible)

    def test_ecole_droits_et_heritage_visibilite_separe(self):
        url = reverse("adaptation_competence_ecole", args=[self.competence.pk])
        self.assertEqual(self.client.get(url, self.parametres).status_code, 403)
        self.client.force_login(self.direction)
        page = self.client.get(url, self.parametres)
        self.assertEqual(self.client.post(url, {**self.parametres, "jeton": page.context["jeton"],
            "mode_libelle": "personnel", "libelle": "Je me présente", "visibilite": "masquer"}).status_code, 302)
        self.client.force_login(self.enseignant)
        self.assertContains(self.page(), "Je me présente")
        self.enregistrer(visibilite="montrer")
        self.assertContains(self.client.get(reverse("choisir_competence", args=[self.classe.pk])), "Je me présente")

    def test_signature_compte_et_annee(self):
        page = self.page()
        self.assertEqual(self.enregistrer(page, jeton="invalide").status_code, 400)
        self.client.force_login(self.direction)
        self.assertEqual(self.enregistrer(page).status_code, 400)
        url = reverse("adaptation_competence_ecole", args=[self.competence.pk])
        page = self.client.get(url, self.parametres)
        self.assertEqual(self.client.post(url, {**self.parametres, "annee": "2024-2025",
            "jeton": page.context["jeton"], "mode_libelle": "garder", "visibilite": "montrer"}).status_code, 400)
        self.assertFalse(AdaptationCompetence.objects.exists())

    def test_classe_close_consultable_et_pdf_garde_dernier_libelle(self):
        self.enregistrer(mode_libelle="personnel", libelle="Je me présente", visibilite="montrer")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            clore(utilisateur=self.enseignant, classe=self.classe)
            page = self.page()
            self.assertContains(page, "Je me présente")
            self.assertNotContains(page, "Enregistrer les choix")
            self.assertEqual(self.enregistrer(page, visibilite="masquer").status_code, 400)
            pdf = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]))
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_classe_sans_base_et_version_non_disponible(self):
        from .models import Classe
        autre = Classe.objects.create(ecole=self.ecole, nom="Lucioles fictives", annee_scolaire=self.annee)
        self.client.force_login(self.direction)
        page = self.client.get(reverse("adaptations_classe", args=[autre.pk]))
        self.assertContains(page, "Choisissez d'abord une base")
        self.assertEqual(self.client.get(self.url, {"version": 99999}).status_code, 404)
        self.assertEqual(self.client.get(reverse("adaptations_ecole"), {"annee": "2026-2028"}).status_code, 400)
