from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from .models import Classe, Competence, Domaine, Ecole, FormulationProposee, FormulationLocale, ReglagePresentation
from .presentation import catalogue_icones, formulations_effectives, illustration_effective, propositions
from .services.presentation import enregistrer_formulation, enregistrer_reglage
from .tests import Base


def image_fictive(nom="illustration.png"):
    contenu = BytesIO()
    Image.new("RGB", (40, 30), "#d7e8cd").save(contenu, format="PNG")
    return SimpleUploadedFile(nom, contenu.getvalue(), content_type="image/png")


class HeritagePresentation(Base):
    def test_icone_facultative_et_choix_hierarchiques(self):
        self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).icone, "")
        self.competence.icone = "parler"
        self.competence.save()
        self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).icone, "parler")
        ecole = ReglagePresentation(ecole=self.ecole, competence=self.competence, mode="remplacer", icone="livre")
        enregistrer_reglage(self.direction, ecole)
        effective = illustration_effective(self.ecole, self.competence, self.classe)
        self.assertEqual((effective.icone, effective.provenance), ("livre", "École"))
        classe = ReglagePresentation(ecole=self.ecole, classe=self.classe, competence=self.competence, mode="desactiver")
        enregistrer_reglage(self.enseignant, classe)
        self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).icone, "")
        classe.mode = "heriter"
        enregistrer_reglage(self.enseignant, classe)
        self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).icone, "livre")

    def test_desactivation_ecole_autorise_un_choix_de_classe(self):
        enregistrer_reglage(self.direction, ReglagePresentation(
            ecole=self.ecole, competence=self.competence, mode="desactiver"))
        enregistrer_reglage(self.enseignant, ReglagePresentation(
            ecole=self.ecole, classe=self.classe, competence=self.competence,
            mode="remplacer", icone="collection"))
        self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).icone, "collection")

    def test_formulations_adaptees_individuellement_et_retour_heritage(self):
        f1 = FormulationProposee.objects.create(competence=self.competence, code="F1", texte="<prenom> parle")
        FormulationProposee.objects.create(competence=self.competence, code="F2", texte="<prenom> écoute")
        enregistrer_formulation(utilisateur=self.direction, competence=self.competence,
                                cle=f"base-{f1.pk}", texte="<prenom> raconte")
        self.assertEqual(formulations_effectives(self.competence, self.classe), ["<prenom> raconte", "<prenom> écoute"])
        enregistrer_formulation(utilisateur=self.enseignant, competence=self.competence,
                                classe=self.classe, cle=f"base-{f1.pk}", mode="desactiver")
        self.assertEqual(formulations_effectives(self.competence, self.classe), ["<prenom> écoute"])
        f1.texte = "Nouvelle source"
        f1.save()
        self.assertEqual(formulations_effectives(self.competence), ["<prenom> raconte", "<prenom> écoute"])
        enregistrer_formulation(utilisateur=self.enseignant, competence=self.competence,
                                classe=self.classe, cle=f"base-{f1.pk}", mode="heriter")
        self.assertEqual(formulations_effectives(self.competence, self.classe)[0], "<prenom> raconte")

    def test_ajout_ecole_adaptable_par_classe(self):
        self.assertEqual(formulations_effectives(self.competence), [])
        source = enregistrer_formulation(utilisateur=self.direction, competence=self.competence, texte="Proposition école")
        adaptation = enregistrer_formulation(utilisateur=self.enseignant, competence=self.competence,
                                             classe=self.classe, cle=f"locale-{source.pk}", texte="Proposition classe")
        self.assertEqual(adaptation.origine_locale_id, source.pk)
        self.assertEqual(formulations_effectives(self.competence), ["Proposition école"])
        self.assertEqual(formulations_effectives(self.competence, self.classe), ["Proposition classe"])

    def test_masquage_ne_detruit_pas_les_textes_deja_saisis(self):
        trace = self.creer_trace(commentaire="Texte enregistré")
        f = FormulationProposee.objects.create(competence=self.competence, code="F", texte="Texte fourni")
        enregistrer_formulation(utilisateur=self.direction, competence=self.competence,
                                cle=f"base-{f.pk}", mode="desactiver")
        self.assertEqual(formulations_effectives(self.competence, self.classe), [])
        self.assertEqual(len(propositions(self.competence, self.classe, True)), 1)
        trace.refresh_from_db()
        self.assertEqual(trace.commentaire, "Texte enregistré")

    def test_responsable_ne_modifie_pas_ecole_et_sources_hors_perimetre_refusees(self):
        with self.assertRaises(PermissionDenied):
            enregistrer_reglage(self.enseignant, ReglagePresentation(ecole=self.ecole))
        autre = Competence.objects.create(domaine=self.competence.domaine, code="AUTRE", libelle="Autre")
        f = FormulationProposee.objects.create(competence=autre, code="F", texte="Autre proposition")
        with self.assertRaises(PermissionDenied):
            enregistrer_formulation(utilisateur=self.enseignant, competence=self.competence,
                                    classe=self.classe, cle=f"base-{f.pk}", texte="Intrusion")
        autre_ecole = Ecole.objects.create(nom="Autre école")
        autre_classe = Classe.objects.create(ecole=autre_ecole, nom="Autre classe")
        with self.assertRaises(PermissionDenied):
            enregistrer_formulation(utilisateur=self.direction, competence=self.competence,
                                    classe=autre_classe, texte="Intrusion")

    def test_import_yaml_met_a_jour_source_sans_ecraser_adaptation(self):
        f = FormulationProposee.objects.create(competence=self.competence, code="F1", texte="Source")
        enregistrer_formulation(utilisateur=self.direction, competence=self.competence,
                                cle=f"base-{f.pk}", texte="Adaptation conservée")
        with TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "reference.yaml"
            fichier.write_text("domaines:\n  - code: LANG\n    nom: Langage\n    competences:\n      - code: LANG-01\n        libelle: Mise à jour\n        icone: parler\n        formulations:\n          - code: F1\n            texte: Nouvelle source\n", encoding="utf-8")
            call_command("charger_referentiel", str(fichier), ecole=self.ecole.pk, stdout=StringIO())
            f.refresh_from_db()
            self.competence.refresh_from_db()
            self.assertEqual(f.texte, "Nouvelle source")
            self.assertEqual(self.competence.icone, "parler")
            self.assertEqual(formulations_effectives(self.competence, self.classe), ["Adaptation conservée"])
            fichier.write_text(fichier.read_text().replace("icone: parler", "icone: inexistante"), encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("charger_referentiel", str(fichier), ecole=self.ecole.pk, stdout=StringIO())

    def test_svg_fournis_disponibles_pour_collectstatic_et_paquet(self):
        self.assertEqual(len(catalogue_icones()), 3)
        for icone in catalogue_icones().values():
            self.assertTrue(finders.find(icone["fichier"]))
        spec = (Path(__file__).resolve().parents[1] / "scripts" / "PetitsPas.spec").read_text()
        self.assertIn('str(racine / "referentiel")', spec)


class ParcoursPresentation(Base):
    def test_icone_effective_dans_listes_et_ligne_htmx(self):
        self.competence.icone = "livre"
        self.competence.save()
        self.client.force_login(self.enseignant)
        urls = [reverse("saisie_eleve", args=[self.eleve.pk]),
                reverse("choisir_competence", args=[self.classe.pk])]
        for url in urls:
            self.assertContains(self.client.get(url), 'class="icone-liste"')
        ligne = self.client.post(reverse("basculer", args=[self.eleve.pk, self.competence.pk]),
                                 HTTP_HX_REQUEST="true")
        self.assertContains(ligne, 'class="icone-liste"')
        enregistrer_reglage(self.enseignant, ReglagePresentation(
            ecole=self.ecole, classe=self.classe, competence=self.competence, mode="desactiver"))
        for url in urls:
            self.assertNotContains(self.client.get(url), 'class="icone-liste"')

    def test_heritage_ignore_modifications_image_et_aides_repliees(self):
        reglage = enregistrer_reglage(self.direction, ReglagePresentation(
            ecole=self.ecole, competence=self.competence, mode="remplacer", icone="livre"))
        self.client.force_login(self.direction)
        url = reverse("presentation_competence_ecole", args=[self.competence.pk])
        self.assertEqual(self.client.post(url, {"mode": "heriter", "icone": "parler"}).status_code, 302)
        reglage.refresh_from_db()
        self.assertEqual(reglage.icone, "livre")
        page = self.client.get(url)
        self.assertContains(page, '<details class="aide-presentation">', count=4)
        self.assertContains(page, 'id="icones-apercu"')
        self.assertNotContains(page, 'details open')

    def test_adaptation_et_retour_a_heritage_depuis_interface(self):
        source = FormulationProposee.objects.create(competence=self.competence, code="F", texte="Source")
        self.client.force_login(self.enseignant)
        url = reverse("presentation_competence_classe", args=[self.classe.pk, self.competence.pk])
        self.assertEqual(self.client.post(url, {"action": "formulation", "cle": f"base-{source.pk}",
                                              "mode": "remplacer", "texte": "Adaptation"}).status_code, 302)
        self.assertEqual(formulations_effectives(self.competence, self.classe), ["Adaptation"])
        self.assertEqual(self.client.post(url, {"action": "formulation", "cle": f"base-{source.pk}",
                                              "mode": "heriter", "texte": "Adaptation"}).status_code, 302)
        self.assertEqual(formulations_effectives(self.competence, self.classe), ["Source"])

    def test_remplacer_photo_par_icone_et_nettoyer_ancien_fichier(self):
        with TemporaryDirectory() as dossier, override_settings(MEDIA_ROOT=dossier):
            self.client.force_login(self.direction)
            url = reverse("presentation_competence_ecole", args=[self.competence.pk])
            self.assertEqual(self.client.post(url, {"mode": "remplacer", "photo": image_fictive()}).status_code, 302)
            reglage = ReglagePresentation.objects.get()
            ancien = reglage.photo.path
            self.assertNotContains(self.client.get(url), reglage.photo.url)
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(url, {"mode": "remplacer", "icone": "parler",
                                                       "photo-clear": "on"}).status_code, 302)
            reglage.refresh_from_db()
            self.assertFalse(reglage.photo)
            self.assertEqual(reglage.icone, "parler")
            self.assertFalse(Path(ancien).exists())

    def test_reglages_ecole_et_classe_accessibles_selon_role(self):
        self.client.force_login(self.direction)
        self.assertEqual(self.client.get(reverse("presentation_ecole")).status_code, 200)
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(reverse("presentation_classe", args=[self.classe.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("presentation_ecole")).status_code, 403)

    def test_refus_ecole_propose_la_meme_competence_dans_classe_autorisee(self):
        self.client.force_login(self.enseignant)
        url = reverse("presentation_competence_ecole", args=[self.competence.pk])
        cible = reverse("presentation_competence_classe", args=[self.classe.pk, self.competence.pk])
        page = self.client.get(url)
        self.assertContains(page, "Ces réglages concernent toute l'école", status_code=403)
        self.assertContains(page, cible, status_code=403)
        self.assertEqual(self.client.get(cible).status_code, 200)
        page = self.client.post(url, {"mode": "remplacer", "icone": "livre"})
        self.assertEqual(page.status_code, 403)
        self.assertFalse(ReglagePresentation.objects.exists())

    def test_proposition_classe_dans_formulaires_individuel_et_collectif(self):
        enregistrer_formulation(utilisateur=self.enseignant, competence=self.competence,
                                classe=self.classe, texte="<prénom> observe les formes")
        self.client.force_login(self.enseignant)
        self.assertContains(self.client.get(reverse("trace", args=[self.eleve.pk, self.competence.pk])), "Lou observe les formes")
        page = self.client.get(reverse("ajouter_trace_commune", args=[self.classe.pk, self.competence.pk]))
        self.assertContains(page, "&lt;prénom&gt; observe les formes")

    def test_icone_suit_les_regles_de_selection_du_carnet(self):
        self.competence.icone = "parler"
        self.competence.save()
        self.client.force_login(self.enseignant)
        url = reverse("carnet", args=[self.eleve.pk])
        self.assertNotContains(self.client.get(url, {"contenu": "reussites"}), 'class="icone-competence"')
        self.assertContains(self.client.get(url, {"contenu": "tout"}), 'class="icone-competence"')
        enregistrer_reglage(self.enseignant, ReglagePresentation(
            ecole=self.ecole, classe=self.classe, competence=self.competence, mode="desactiver"))
        self.assertNotContains(self.client.get(url, {"contenu": "tout"}), 'class="icone-competence"')

    def test_photo_couverture_privee_et_pdf_avec_svg(self):
        self.competence.icone = "livre"
        self.competence.save()
        with TemporaryDirectory() as dossier, override_settings(MEDIA_ROOT=dossier):
            self.client.force_login(self.direction)
            page = self.client.post(reverse("presentation_ecole"), {
                "mode": "remplacer", "photo": image_fictive(), "action": "illustration",
            })
            self.assertEqual(page.status_code, 302)
            reglage = ReglagePresentation.objects.get(ecole=self.ecole)
            self.client.force_login(self.enseignant)
            self.assertEqual(self.client.get(reverse("media_presentation", args=[reglage.pk])).status_code, 200)
            page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
            self.assertContains(page, 'class="photo-couverture"')
            pdf = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]), {"contenu": "tout"})
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF"))
            call_command("verifier_reprise_restauree", stdout=StringIO())
            reglage.mode = "desactiver"
            enregistrer_reglage(self.direction, reglage)
            self.assertEqual(self.client.get(reverse("media_presentation", args=[reglage.pk])).status_code, 404)

    def test_media_de_classe_hors_affectation_refuse(self):
        autre_classe = Classe.objects.create(ecole=self.ecole, nom="Autre classe")
        with TemporaryDirectory() as dossier, override_settings(MEDIA_ROOT=dossier):
            reglage = ReglagePresentation.objects.create(ecole=self.ecole, classe=autre_classe,
                                                         mode="remplacer", photo=image_fictive())
            self.client.force_login(self.enseignant)
            self.assertEqual(self.client.get(reverse("media_presentation", args=[reglage.pk])).status_code, 404)

    def test_image_invalide_ne_modifie_pas_reglage(self):
        self.client.force_login(self.direction)
        fichier = SimpleUploadedFile("faux.png", b"pas une image", content_type="image/png")
        page = self.client.post(reverse("presentation_ecole"), {"mode": "remplacer", "photo": fichier})
        self.assertEqual(page.status_code, 200)
        self.assertFalse(ReglagePresentation.objects.exists())
