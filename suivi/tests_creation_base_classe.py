"""Le défaut prépare une base fixe, sans confirmation séparée ni acquis."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse

from .tests import Base
from .tests_import_sources_referentiels import document, importer
from .services.reprise_referentiels import reprendre
from .models import AdoptionReferentiel, Classe, Observation, EtatAnnuelObservation
from .services.choix_bases_referentiels import (choix_bases, enregistrer_choix_ecole,
                                              publier_choix_application)
from .services.garde_fous_referentiels import demarrage_ecole
from .services.creation_classe import creer_classe_avec_base
from .services.adoption_bases_referentiels import adopter_base, apercu_adoption


class CreationBaseClasse(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.annee = self.classe.annee_scolaire
        self.a = importer(document("creation-a"))[0]
        self.b = importer(document("creation-b"))[0]
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.client.force_login(self.direction)
        self.creation = reverse("creer_classe")

    def creer(self, **options):
        page = self.client.get(self.creation, {"annee_scolaire": self.annee})
        donnees = dict(nom="Nouvelle classe fictive", annee_scolaire=self.annee, base="ecole",
                       jeton_choix=page.context["formulaire"]["jeton_choix"].value())
        donnees.update(options)
        return self.client.post(self.creation, donnees)

    def test_defaut_adopte_a_la_creation_sans_mot_de_passe_ni_saisie(self):
        page = self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        self.assertRedirects(page, reverse("importer_eleves", args=[classe.pk]))
        adoption = AdoptionReferentiel.objects.get(classe=classe)
        self.assertEqual(adoption.version_id, self.a.pk)
        self.assertTrue(adoption.initialisee_depuis_ecole)
        self.assertEqual(adoption.auteur_id, self.direction.pk)
        self.assertTrue(adoption.usages.exists())
        self.assertFalse(Observation.objects.exists())
        self.assertFalse(EtatAnnuelObservation.objects.exists())
        self.assertTrue(demarrage_ecole(self.ecole))
        self.assertFalse(classe.responsables_actifs().exists())
        self.assertEqual(classe.etat, Classe.PREPARATION)
        # Une proposition d'école ultérieure ne remplace pas cette adoption.
        choix = choix_bases(self.ecole, self.annee)
        enregistrer_choix_ecole(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            restreindre=False, versions_ids=[], proposee_id=self.b.pk, revisions_attendues=choix.revisions)
        adoption.refresh_from_db()
        self.assertEqual(adoption.version_id, self.a.pk)
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=classe).count(), 1)

    def test_choix_independant_exige_mot_de_passe_meme_pour_le_defaut(self):
        page = self.creer(base=str(self.a.pk))
        self.assertContains(page, "Saisissez votre mot de passe")
        self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
        self.creer(base=str(self.a.pk), mot_de_passe="dir-mdp")
        adoption = AdoptionReferentiel.objects.get(classe__nom="Nouvelle classe fictive")
        self.assertFalse(adoption.initialisee_depuis_ecole)
        self.assertFalse(demarrage_ecole(self.ecole))

    def test_autre_base_choisie_explicitement_et_sans_droit_pedagogique(self):
        self.creer(base=str(self.b.pk), mot_de_passe="dir-mdp")
        adoption = AdoptionReferentiel.objects.get(classe__nom="Nouvelle classe fictive")
        self.assertEqual(adoption.version_id, self.b.pk)
        self.assertFalse(adoption.initialisee_depuis_ecole)
        self.assertFalse(adoption.classe.responsables_actifs().exists())

    def test_absence_de_catalogue_n_empeche_pas_preparation_sans_base(self):
        self.annee = "2027-2028"
        # La reprise locale reste proposée tant qu'aucune politique n'est publiée.
        publier_choix_application(annee=self.annee, versions_ids=[], proposee_id=None, revision_attendue=0)
        self.creer(base="plus_tard")
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        self.assertEqual(classe.annee_scolaire, self.annee)
        self.assertFalse(AdoptionReferentiel.objects.filter(classe=classe).exists())

    def test_restriction_et_annee_cible_controlees(self):
        choix = choix_bases(self.ecole, self.annee)
        enregistrer_choix_ecole(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
            restreindre=True, versions_ids=[self.a.pk], proposee_id=self.a.pk,
            revisions_attendues=choix.revisions)
        page = self.creer(base=str(self.b.pk), mot_de_passe="dir-mdp")
        self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
        self.assertContains(page, "Sélectionnez un choix valide")
        publier_choix_application(annee="2027-2028", versions_ids=[self.b.pk],
                                 proposee_id=self.b.pk, revision_attendue=0)
        self.annee = "2027-2028"
        self.creer()
        self.assertEqual(AdoptionReferentiel.objects.get(classe__nom="Nouvelle classe fictive").version_id, self.b.pk)

    def test_jeton_perime_et_annee_modifiee_ne_creent_rien(self):
        page = self.client.get(self.creation, {"annee_scolaire": self.annee})
        jeton = page.context["formulaire"]["jeton_choix"].value()
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.b.pk, revision_attendue=1)
        for donnees in (dict(annee_scolaire=self.annee, base="ecole"),
                        dict(annee_scolaire="2027-2028", base="ecole")):
            reponse = self.client.post(self.creation, dict(nom="Refusée", jeton_choix=jeton, **donnees))
            self.assertContains(reponse, "Vérifiez")
            self.assertFalse(Classe.objects.filter(nom="Refusée").exists())

    def test_echec_adoption_annule_creation_et_nom_duplique_ne_modifie_pas(self):
        with patch("suivi.services.creation_classe.adopter_base", side_effect=ValidationError("Refus fictif")):
            self.assertContains(self.creer(), "Refus fictif")
        self.assertFalse(Classe.objects.filter(nom="Nouvelle classe fictive").exists())
        self.creer()
        avant = list(AdoptionReferentiel.objects.values())
        self.assertContains(self.creer(), "Cette classe existe déjà")
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)

    def test_origine_initiale_ne_peut_pas_etre_utilisee_pour_un_remplacement(self):
        self.creer()
        classe = Classe.objects.get(nom="Nouvelle classe fictive")
        apercu = apercu_adoption(utilisateur=self.direction, classe=classe, version_id=self.b.pk)
        with self.assertRaises(ValidationError):
            adopter_base(utilisateur=self.direction, classe=classe, version_id=self.b.pk,
                revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
                garde_attendue=apercu["garde"]["empreinte"], initialisee_depuis_ecole=True)
        self.assertEqual(AdoptionReferentiel.objects.get(classe=classe).version_id, self.a.pk)

    def test_creation_reste_reservee_direction(self):
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(self.creation).status_code, 403)
        self.assertEqual(self.client.post(self.creation, {"nom": "Interdite"}).status_code, 403)
