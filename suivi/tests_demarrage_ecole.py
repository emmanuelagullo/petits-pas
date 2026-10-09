"""Le démarrage ne change aucune adoption ni autorisation technique."""
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from .tests import Base
from .tests_import_sources_referentiels import document, importer
from .models import (AdaptationCompetence, AdoptionReferentiel, ChoixEcoleAnnuel,
                     Classe, Observation, TraceCommune)
from .services.reprise_referentiels import reprendre
from .services.garde_fous_referentiels import demarrage_ecole
from .services.choix_bases_referentiels import (choix_bases, publier_choix_application,
                                               enregistrer_choix_ecole)
from .services.adoption_bases_referentiels import adopter_base, apercu_adoption


class DemarrageEcole(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.annee = self.classe.annee_scolaire
        self.a = importer(document("demarrage-a"))[0]
        self.b = importer(document("demarrage-b"))[0]
        publier_choix_application(annee=self.annee, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.client.force_login(self.direction)
        self.url = reverse("referentiels_ecole")

    def apercu(self, **options):
        donnees = dict(action="apercu", annee=self.annee, autorisations="garder",
                       proposee=self.b.pk)
        donnees.update(options)
        return self.client.post(self.url, donnees)

    def confirmer(self, page, **options):
        donnees = dict(action="confirmer", annee=self.annee, jeton=page.context["jeton"])
        donnees.update(options)
        return self.client.post(self.url, donnees)

    def test_prechargement_et_classes_sans_choix_ne_sont_pas_des_saisies(self):
        self.assertTrue(demarrage_ecole(self.ecole))
        avant = list(AdoptionReferentiel.objects.values())
        page = self.apercu()
        self.assertContains(page, "Préparation initiale")
        self.assertNotContains(page, "Votre mot de passe")
        self.assertEqual(self.confirmer(page).status_code, 302)
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.b.pk)

    def test_ecole_sans_classe_accueil_et_gestion_ordonnent_les_etapes(self):
        from .models import Ecole
        from comptes.models import AppartenanceEcole, ResponsabiliteEcole
        neuve = Ecole.objects.create(nom="École fictive neuve")
        appartenance = AppartenanceEcole.objects.create(ecole=neuve, utilisateur=self.direction)
        ResponsabiliteEcole.objects.create(appartenance=appartenance, type=ResponsabiliteEcole.DIRECTION)
        session = self.client.session
        session["ecole_id"] = neuve.pk
        session.save()
        for nom in ("accueil", "gestion"):
            page = self.client.get(reverse(nom))
            self.assertContains(page, "Choisir ou valider les propositions de référentiels")
            texte = page.content.decode()
            self.assertLess(texte.index("Choisir ou valider"), texte.index("Créer les classes"))
            self.assertLess(texte.index("Créer les classes"), texte.index("Inviter l’équipe"))

    def test_adoption_du_defaut_est_un_choix_explicite_pas_un_heritage(self):
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Nouvelle", annee_scolaire=self.annee)
        apercu = apercu_adoption(utilisateur=self.direction, classe=nouvelle, version_id=self.a.pk)
        adopter_base(utilisateur=self.direction, classe=nouvelle, version_id=self.a.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=None,
            garde_attendue=apercu["garde"]["empreinte"])
        self.assertFalse(demarrage_ecole(self.ecole))
        page = self.apercu()
        self.assertContains(page, "Votre mot de passe")
        self.assertEqual(self.confirmer(page).status_code, 400)
        avant = list(AdoptionReferentiel.objects.values())
        self.assertEqual(self.confirmer(page, mot_de_passe="dir-mdp").status_code, 302)
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)

    def test_adaptation_et_ancien_choix_independant_imposent_precaution(self):
        adaptation = AdaptationCompetence.objects.create(ecole=self.ecole,
            annee_scolaire="2025-2026", competence=self.competence, libelle="Texte fictif")
        self.assertFalse(demarrage_ecole(self.ecole))
        self.assertContains(self.apercu(), "Votre mot de passe")
        adaptation.delete()
        adoption = AdoptionReferentiel.objects.get(classe=self.classe)
        adoption.auteur = self.direction
        adoption.courante = False
        adoption.save()
        self.assertFalse(demarrage_ecole(self.ecole))

    def test_observation_trace_retiree_et_trace_commune_sont_des_saisies(self):
        observation = Observation.objects.create(eleve=self.eleve, competence=self.competence)
        self.assertFalse(demarrage_ecole(self.ecole))
        observation.delete()
        trace = self.creer_trace(supprime_le=timezone.now())
        self.assertFalse(demarrage_ecole(self.ecole))
        trace.delete()
        Observation.objects.all().delete()
        TraceCommune.objects.create(classe=self.classe, competence=self.competence,
                                    commentaire="Fictif", auteur=self.enseignant, supprime_le=timezone.now())
        self.assertFalse(demarrage_ecole(self.ecole))

    def test_nouvelle_saisie_entre_apercu_et_confirmation_refuse_jeton(self):
        page = self.apercu()
        self.creer_trace()
        self.assertEqual(self.confirmer(page, mot_de_passe="dir-mdp").status_code, 400)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())
        with self.assertRaises(ValidationError):
            enregistrer_choix_ecole(utilisateur=self.direction, ecole=self.ecole,
                annee=self.annee, restreindre=False, versions_ids=[], proposee_id=self.b.pk,
                revisions_attendues=choix_bases(self.ecole, self.annee).revisions,
                demarrage_attendu=True)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_restriction_initiale_reste_orange_et_annees_independantes(self):
        page = self.apercu(autorisations="restreindre", versions=[self.b.pk])
        self.assertContains(page, "avertissement-orange")
        self.assertContains(page, "Votre mot de passe")
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertEqual(self.confirmer(page, mot_de_passe="dir-mdp").status_code, 302)
        page = self.apercu(annee="2027-2028", proposee=self.b.pk)
        self.assertEqual(page.status_code, 400)  # Catalogue importé, mais pas autorisé cette année.
        self.assertEqual(len(choix_bases(self.ecole, self.annee).versions), 1)

    def test_offre_absente_explique_sans_importer_ni_publier(self):
        from .models import ChoixApplicationAnnuel, VersionReferentiel
        avant = (VersionReferentiel.objects.count(), ChoixApplicationAnnuel.objects.count())
        page = self.client.get(self.url, {"annee": "2027-2028"})
        self.assertContains(page, "Pourquoi un référentiel manque-t-il ?")
        self.assertContains(page, "Sans publication annuelle")
        self.assertEqual((VersionReferentiel.objects.count(), ChoixApplicationAnnuel.objects.count()), avant)
        self.client.force_login(self.enseignant)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_retirer_une_restriction_initiale_demande_aussi_mot_de_passe(self):
        self.confirmer(self.apercu(autorisations="restreindre", versions=[self.b.pk]),
                       mot_de_passe="dir-mdp")
        page = self.apercu(proposee=self.a.pk)
        self.assertContains(page, "Votre mot de passe")
        self.assertEqual(self.confirmer(page).status_code, 400)
        self.assertTrue(ChoixEcoleAnnuel.objects.get().restreindre)
