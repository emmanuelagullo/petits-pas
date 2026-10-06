from tempfile import TemporaryDirectory

from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from .models import Competence, ReglagePresentation, RessourceReferentiel
from .presentation import illustration_effective
from .referentiels import arbre_competences
from .services.cloture_referentiels import clore
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_presentation import image_fictive
from .views import _supprimer_media_apres_validation


class LectureEtCloture(Base):
    def setUp(self):
        super().setUp()
        self.trace_initiale = self.creer_trace(commentaire="Trace conservée")
        self.competence.icone = "parler"
        self.competence.save()
        reprendre(self.ecole.pk)

    def test_lecture_version_et_non_catalogue_modifie(self):
        Competence.objects.filter(pk=self.competence.pk).update(libelle="Modification directe")
        domaine = arbre_competences(self.ecole, classe=self.classe)[0]
        self.assertEqual(domaine.visibles[0].libelle, "Je dis mon prénom")
        self.assertEqual(domaine.pk, self.competence.domaine_id)
        with self.assertRaises(ValueError):
            from .models import Ecole
            arbre_competences(Ecole.objects.create(nom="Autre école fictive"), classe=self.classe)

    def test_masquage_conserve_ligne_du_carnet(self):
        Competence.objects.filter(pk=self.competence.pk).update(active=False)
        self.assertFalse(arbre_competences(self.ecole, classe=self.classe)[0].visibles)
        self.assertEqual(len(arbre_competences(self.ecole, classe=self.classe,
                                             inclure_ids=[self.competence.pk])[0].visibles), 1)
        self.entrer()
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]))
        self.assertContains(page, "Trace conservée")

    def test_cloture_conserve_icone_et_refuse_saisie(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            adoption = clore(utilisateur=self.enseignant, classe=self.classe)
            image = illustration_effective(self.ecole, self.competence, self.classe)
            self.assertTrue(adoption.clos)
            self.assertTrue(image.photo.endswith(".svg"))
            self.assertTrue(RessourceReferentiel.objects.filter(pk=image.ressource_id).exists())
            self.competence.icone = "livre"
            self.competence.save()
            self.assertEqual(illustration_effective(self.ecole, self.competence, self.classe).photo, image.photo)
            with self.assertRaises(PermissionDenied):
                modifier_etat(utilisateur=self.enseignant, eleve=self.eleve,
                              competence=self.competence, statut="en_cours")
            self.assertEqual(clore(utilisateur=self.enseignant, classe=self.classe).pk, adoption.pk)
            self.entrer()
            self.assertEqual(self.client.get(reverse("media_referentiel", args=[self.eleve.pk, image.ressource_id])).status_code, 200)

    def test_photo_finale_protegee_du_nettoyage(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            reglage = ReglagePresentation.objects.create(ecole=self.ecole, classe=self.classe,
                competence=self.competence, mode="remplacer", photo=image_fictive(),
                photo_pdf=image_fictive("illustration-pdf.png"))
            nom = reglage.photo.name
            nom_pdf = reglage.photo_pdf.name
            stockage = reglage.photo.storage
            clore(utilisateur=self.enseignant, classe=self.classe)
            reglage.photo = None
            reglage.photo_pdf = None
            reglage.mode = "desactiver"
            reglage.save()
            with self.captureOnCommitCallbacks(execute=True):
                _supprimer_media_apres_validation(nom)
                _supprimer_media_apres_validation(nom_pdf)
            self.assertTrue(stockage.exists(nom))
            self.assertTrue(stockage.exists(nom_pdf))
            ressource = RessourceReferentiel.objects.get(fichier=nom)
            self.assertEqual(ressource.fichier_pdf.name, nom_pdf)

    def test_cloture_refusee_sans_droit(self):
        from comptes.models import Utilisateur
        utilisateur = Utilisateur.objects.create_user(username="sans-droit-fictif")
        with self.assertRaises(PermissionDenied):
            clore(utilisateur=utilisateur, classe=self.classe)


class RessourcesInitiales(Base):
    def test_reprise_protege_photo_initiale_meme_si_reglage_remplace(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            reglage = ReglagePresentation.objects.create(ecole=self.ecole,
                competence=self.competence, mode="remplacer", photo=image_fictive())
            nom = reglage.photo.name
            stockage = reglage.photo.storage
            reprendre(self.ecole.pk)
            reglage.photo = None
            reglage.mode = "desactiver"
            reglage.save()
            with self.captureOnCommitCallbacks(execute=True):
                _supprimer_media_apres_validation(nom)
            self.assertTrue(stockage.exists(nom))
            self.assertTrue(RessourceReferentiel.objects.filter(fichier=nom).exists())

    def test_cloture_ne_prend_pas_etat_d_une_annee_ulterieure(self):
        from .models import Classe, Scolarite, Observation
        self.creer_trace(commentaire="Trace fictive avant changement")
        reprendre(self.ecole.pk)
        annee = f"{int(self.classe.annee_scolaire[:4]) + 1}-{int(self.classe.annee_scolaire[:4]) + 2}"
        suivante = Classe.objects.create(ecole=self.ecole, nom="Hirondelles", annee_scolaire=annee)
        Scolarite.objects.create(eleve=self.eleve, classe=suivante, annee_scolaire=annee, niveau="MS")
        Observation.objects.filter(eleve=self.eleve, competence=self.competence).update(statut="reussi")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            adoption = clore(utilisateur=self.enseignant, classe=self.classe)
        self.assertFalse(adoption.etat_final["etats"][0]["connu"])
        self.assertIsNone(adoption.etat_final["etats"][0]["statut"])
