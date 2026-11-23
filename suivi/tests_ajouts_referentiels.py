from tempfile import TemporaryDirectory
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from .models import AdoptionReferentiel, Classe, CompetenceLocale, EtatAnnuelObservation, Observation
from .referentiels import contenu_adoption, contenu_origine
from .services.ajouts_referentiels import creer_ajout, proposer_ajout, reprendre_ajout
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.contextes_referentiels import usage_pour_saisie
from .services.cloture_referentiels import clore
from .services.pedagogie import modifier_etat
from .services.suivi_libre import associer
from . import tests_adoption_bases_referentiels as fixtures
from .tests import Base


class AjoutsLocaux(Base):
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

    adopter = fixtures.AdoptionBases.adopter
    def creer(self, classe=True, **options):
        adoption = self.adopter()
        return creer_ajout(utilisateur=self.enseignant if classe else self.direction, ecole=self.ecole,
            annee=self.classe.annee_scolaire, classe=self.classe if classe else None,
            adoption_attendue=adoption.pk if classe else None,
            domaine_id=adoption.contenu["domaines"][0]["id"], libelle="Je trie des objets fictifs", niveau="PS", **options)

    def test_partage_portable_sans_donnees_de_suivi(self):
        from .models import Ecole
        from .services.import_sources_referentiels import importer_source
        from .services.paquets_referentiels import lire_paquet
        from .services.versions_sources_ecoles import definir_version_ecole

        locale = self.creer()
        url = reverse("ajout_classe", args=[self.classe.pk, locale.pk])
        paquet = self.client.post(url, {"action": "partager", "provenance": "Équipe pédagogique",
                                         "licence": "CC-BY-SA-4.0", "icone": "parler"})
        self.assertEqual(paquet["Content-Type"], "application/zip")
        document = lire_paquet(paquet.content)
        autre = Ecole.objects.create(nom="Autre école fictive")
        version, cree, _ = importer_source(document, ecole=autre)
        self.assertTrue(cree)
        self.assertEqual(importer_source(document, ecole=autre)[:2], (version, False))
        self.assertNotEqual(definir_version_ecole(autre, version)["competences"][0]["id"], locale.competence_id)
        version_retour, _, _ = importer_source(document, ecole=self.ecole)
        self.assertEqual(definir_version_ecole(self.ecole, version_retour)["competences"][0]["id"], locale.competence_id)

    def test_partage_icone_png_et_projection(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from .models import Ecole, IconePartagee
        from .services.import_sources_referentiels import importer_source
        from .services.paquets_referentiels import lire_paquet
        from .services.versions_sources_ecoles import definir_version_ecole
        from .icones_partagees import decoder_icone, png_en_ligne

        locale = self.creer()
        image = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(image, format="PNG")
        url = reverse("ajout_classe", args=[self.classe.pk, locale.pk])
        paquet = self.client.post(url, {"action": "partager", "provenance": "Équipe",
            "licence": "CC-BY-SA-4.0", "icone_generique": "oui",
            "icone_png": SimpleUploadedFile("cercle.png", image.getvalue())})
        self.assertEqual(paquet["Content-Type"], "application/zip")
        ecole = Ecole.objects.create(nom="Destinataire fictif")
        version, _, _ = importer_source(lire_paquet(paquet.content), ecole=ecole)
        definition = definir_version_ecole(ecole, version)["competences"][0]
        with Image.open(BytesIO(decoder_icone(png_en_ligne(definition["icone_png"])))) as icone:
            self.assertEqual(icone.size, (16, 16))
            self.assertEqual(icone.getpixel((0, 0)), (0, 0, 255, 255))

        from zipfile import ZipFile
        from .services.paquets_referentiels import exporter_paquet
        from .presentation import illustration_effective
        from .models import Competence
        from .exports_ecole import selections

        with ZipFile(BytesIO(paquet.content)) as archive:
            self.assertEqual(len([nom for nom in archive.namelist() if nom.endswith(".png")]), 1)
            self.assertIn(b"sha256:", archive.read("referentiel.yaml"))
        ancien_zip = BytesIO()
        with ZipFile(ancien_zip, "w") as archive:
            archive.writestr("referentiel.yaml", lire_paquet(paquet.content))
        version_retour, _, _ = importer_source(lire_paquet(ancien_zip.getvalue()), ecole=self.ecole)
        self.assertEqual(IconePartagee.objects.count(), 1)
        from .services.import_sources_referentiels import lire_source
        self.assertEqual(lire_source(lire_paquet(exporter_paquet(version_retour))),
                         lire_source(lire_paquet(paquet.content)))
        self.assertEqual(IconePartagee.objects.filter(selections(ecole.pk)[IconePartagee]).count(), 1)

        adoption = self.adopter(version_retour)
        competence = Competence.objects.get(pk=adoption.contenu["competences"][0]["id"])
        self.assertTrue(illustration_effective(self.ecole, competence, self.classe).url_png)
        clore(utilisateur=self.enseignant, classe=self.classe)
        self.assertTrue(illustration_effective(self.ecole, competence, self.classe).url_png)
        from .views import _generer_pdf
        from unittest.mock import patch
        with patch("suivi.views._generer_pdf", wraps=_generer_pdf) as generer:
            pdf = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn("data:image/png;base64,", generer.call_args.args[0])



    def test_partage_uniquement_les_phrases_cochees(self):
        from .services.import_sources_referentiels import lire_source
        from .services.paquets_referentiels import lire_paquet
        from .services.presentation import enregistrer_formulation

        locale = self.creer()
        partagee = enregistrer_formulation(utilisateur=self.enseignant, competence=locale.competence,
                                          classe=self.classe, texte="Je trie par forme.")
        enregistrer_formulation(utilisateur=self.enseignant, competence=locale.competence,
                                classe=self.classe, texte="Je trie par couleur.")
        url = reverse("ajout_classe", args=[self.classe.pk, locale.pk])
        donnees = {"action": "partager", "provenance": "Équipe", "licence": "CC-BY-SA-4.0"}
        for choix, attendues in (([], []), ([f"locale-{partagee.pk}"], ["Je trie par forme."])):
            reponse = self.client.post(url, {**donnees, "phrase": choix})
            self.assertEqual(reponse["Content-Type"], "application/zip")
            contenu, _ = lire_source(lire_paquet(reponse.content))
            phrases = contenu["domaines"][0]["competences"][0]["formulations"]
            self.assertEqual([phrase["texte"] for phrase in phrases], attendues)

    def test_catalogue_reunit_les_ajouts_et_signale_le_meme_libelle(self):
        locale = self.creer()
        cible = self.creer(suivi_libre=True)
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        associer(utilisateur=self.enseignant, classe=self.classe, locale=cible,
                 ids=[self.eleve.pk], adoption_attendue=adoption.pk)
        catalogue = reverse("catalogue_competences", args=[self.classe.pk])
        page = self.client.get(catalogue, {"q": "je trie"})
        self.assertEqual({ligne["locale"].pk: ligne["portee"] for ligne in page.context["lignes"]},
                         {locale.pk: "classe", cible.pk: "cible"})
        self.assertContains(page, "Suivie pour 1 élève")
        ajout = reverse("ajouts_classe", args=[self.classe.pk])
        jeton = self.client.get(ajout).context["jeton"]
        page = self.client.post(ajout, {"action": "creer", "jeton": jeton,
            "libelle": locale.competence.libelle, "niveau": "GS",
            "domaine": adoption.contenu["domaines"][0]["id"]})
        self.assertContains(page, "Une compétence porte déjà ce libellé", status_code=400)
        self.assertEqual(CompetenceLocale.objects.count(), 2)

    def test_correction_du_classement_conserve_identite_et_observation(self):
        locale = self.creer()
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=locale.competence, statut="reussi")
        observation = Observation.objects.get(competence=locale.competence)
        url = reverse("ajout_classe", args=[self.classe.pk, locale.pk])
        jeton = self.client.get(url).context["jeton"]
        self.assertEqual(self.client.post(url, {"action": "classement", "jeton": jeton,
            "niveau": "GS", "domaine": "", "sous_domaine": ""}).status_code, 302)
        locale.refresh_from_db()
        definition = next(c for c in contenu_adoption(adoption)["competences"] if c["id"] == locale.competence_id)
        self.assertEqual(definition["niveau"], "GS")
        self.assertEqual(locale.definition["competences"][0]["niveau"], "PS")
        observation.refresh_from_db()
        self.assertEqual(observation.statut, "reussi")

    def test_creation_distincte_sans_ressources_et_changement_de_base(self):
        locale = self.creer()
        origine = contenu_origine(AdoptionReferentiel.objects.get(classe=self.classe, courante=True))
        self.assertNotIn(locale.competence_id, [c["id"] for c in origine["competences"]])
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=locale.competence, statut="reussi")
        observation = Observation.objects.get(competence=locale.competence)
        avant = list(EtatAnnuelObservation.objects.filter(observation=observation).values())
        adoption = self.adopter(self.b)
        self.assertIn(locale.competence_id, [c["id"] for c in contenu_adoption(adoption)["competences"]])
        self.assertEqual(usage_pour_saisie(self.classe, locale.competence).adoption_id, adoption.pk)
        self.assertEqual(list(EtatAnnuelObservation.objects.filter(observation=observation).values()), avant)
        self.assertEqual(locale.competence.icone, "")
        self.assertFalse(locale.competence.formulations.exists())

    def test_proposition_ne_pousse_pas_aux_classes_et_reprise_est_idempotente(self):
        locale = self.creer(classe=False)
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        self.assertNotIn(locale.competence_id, [c["id"] for c in contenu_adoption(adoption)["competences"]])
        for _ in range(2):
            reprendre_ajout(utilisateur=self.enseignant, ecole=self.ecole, annee=self.classe.annee_scolaire,
                classe=self.classe, locale=locale, adoption_attendue=adoption.pk)
        self.assertEqual(locale.disponibilites.filter(classe=self.classe).count(), 1)
        self.assertFalse(Observation.objects.exists())
        self.assertEqual(CompetenceLocale.objects.count(), 1)

    def test_masquage_et_cloture_figent_ajout_et_libelle(self):
        locale = self.creer()
        adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        def regler(libelle, visible):
            from .models import AdaptationCompetence
            r = AdaptationCompetence.objects.filter(classe=self.classe, competence=locale.competence).first()
            return enregistrer_adaptation(utilisateur=self.enseignant, ecole=self.ecole,
                annee=self.classe.annee_scolaire, classe=self.classe, competence=locale.competence,
                libelle=libelle, visible=visible, revision_attendue=r.revision if r else 0,
                adoption_attendue=adoption.pk)
        regler("Je classe des objets fictifs", False)
        with self.assertRaises(PermissionDenied): usage_pour_saisie(self.classe, locale.competence)
        regler("Je classe des objets fictifs", True)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
        c = next(c for c in contenu_adoption(finale)["competences"] if c["id"] == locale.competence_id)
        self.assertEqual(c["libelle"], "Je classe des objets fictifs")
        with self.assertRaises(ValidationError): regler(None, True)
        locale.definition = {}
        with self.assertRaises(ValidationError): locale.save()

    def test_nouvelle_annee_reprise_explicite_sans_copie_acquis(self):
        locale = self.creer()
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=locale.competence, statut="reussi")
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Classe fictive suivante", annee_scolaire="2027-2028")
        from .models import ReferentielAnnuel
        annuel = ReferentielAnnuel.objects.create(ecole=self.ecole, annee_scolaire=nouvelle.annee_scolaire, version_proposee=self.a)
        ancienne = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        adoption = AdoptionReferentiel.objects.create(classe=nouvelle, annuel=annuel, version=ancienne.version, contenu=ancienne.contenu)
        self.assertNotIn(locale.competence_id, [c["id"] for c in contenu_adoption(adoption)["competences"]])
        proposer_ajout(utilisateur=self.direction, ecole=self.ecole, annee=nouvelle.annee_scolaire, locale=locale)
        avant = list(EtatAnnuelObservation.objects.values())
        reprendre_ajout(utilisateur=self.direction, ecole=self.ecole, annee=nouvelle.annee_scolaire,
            classe=nouvelle, locale=locale, adoption_attendue=adoption.pk)
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), avant)
        self.assertEqual(CompetenceLocale.objects.count(), 1)
        self.assertEqual(locale.classe_origine_id, self.classe.pk)

    def test_droits_et_contexte_perime(self):
        adoption = self.adopter()
        options = dict(ecole=self.ecole, annee=self.classe.annee_scolaire,
            domaine_id=adoption.contenu["domaines"][0]["id"], libelle="Ajout fictif", niveau="PS")
        with self.assertRaises(PermissionDenied): creer_ajout(utilisateur=self.enseignant, **options)
        with self.assertRaises(ValidationError):
            creer_ajout(utilisateur=self.enseignant, classe=self.classe, adoption_attendue=-1, **options)
        self.assertFalse(CompetenceLocale.objects.exists())
