from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from .tests import Base
from .tests_adoption_bases_referentiels import AdoptionBases
from .tests_import_sources_referentiels import document, importer
from .models import (Competence, CompetenceLocale, Eleve, Scolarite, Observation,
                     EleveApprentissage, Trace, EtatAnnuelObservation, AdoptionReferentiel)
from .referentiels import arbre_competences
from .services.import_sources_referentiels import importer_source
from .services.reprise_referentiels import reprendre
from .services.choix_bases_referentiels import publier_choix_application
from .services.suivi_libre import ajouter_reussite, associer
from .services.pedagogie import modifier_etat
from .services.traces_communes import personnaliser, enregistrer_commune, supprimer_commune


class SuiviLibre(Base):
    adopter = AdoptionBases.adopter

    def setUp(self):
        Base.setUp(self)
        reprendre(self.ecole.pk)
        self.a = importer_source((settings.BASE_DIR / "referentiel/structure-cycle1.yaml").read_text())[0]
        self.b = importer(document("base-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.adoption = self.adopter()
        self.autre = Eleve.objects.create(ecole=self.ecole, prenom="Inès")
        self.sc_autre = Scolarite.objects.create(eleve=self.autre, classe=self.classe,
            annee_scolaire=self.classe.annee_scolaire, niveau="PS")
        self.entree = dict(utilisateur=self.enseignant, classe=self.classe,
            domaine_id=self.adoption.contenu["domaines"][0]["id"], libelle="Je raconte ma construction",
            niveau="PS", date_observation=date(2026, 10, 1), adoption_attendue=self.adoption.pk)

    def creer(self, ids=None, **kwargs):
        return ajouter_reussite(ids=ids or [self.eleve.pk], **dict(self.entree, **kwargs))

    def test_structure_seule_sans_fausse_competence(self):
        self.assertEqual(self.adoption.usages.count(), 0)
        arbre = arbre_competences(self.ecole, classe=self.classe)
        self.assertEqual(len(arbre), 5)
        self.assertFalse(any(d.visibles for d in arbre))
        doc = document(); doc["domaines"][0]["competences"] = []
        with self.assertRaises(ValidationError): importer(doc)

    def test_reussite_datee_etat_modifiable_et_identite_distincte(self):
        a = self.creer(); b = self.creer()
        self.assertNotEqual(a.competence_id, b.competence_id)
        trace = Trace.objects.get(observation__competence=a.competence)
        self.assertTrue(trace.reussite)
        self.assertEqual(trace.date_observation, date(2026, 10, 1))
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=a.competence, statut="en_cours")
        trace.refresh_from_db()
        self.assertTrue(trace.reussite)
        self.assertEqual(Observation.objects.get(competence=a.competence).statut, "en_cours")
        self.assertEqual(EtatAnnuelObservation.objects.get(observation__competence=a.competence).statut, "en_cours")

    def test_portee_et_extension_sans_attribution(self):
        a = self.creer()
        with self.assertRaises(PermissionDenied):
            modifier_etat(utilisateur=self.enseignant, eleve=self.autre, competence=a.competence, statut="reussi")
        associer(utilisateur=self.enseignant, classe=self.classe, locale=a,
            ids=[self.autre.pk], adoption_attendue=self.adoption.pk)
        self.assertFalse(Observation.objects.filter(eleve=self.autre).exists())
        self.assertEqual(EleveApprentissage.objects.count(), 2)

    def test_personnalisation_retrait_et_modification_collective(self):
        a = self.creer([self.eleve.pk, self.autre.pk], commentaire="<prenom> raconte")
        commune = a.competence.traces_communes.get()
        trace = personnaliser(utilisateur=self.enseignant, trace=commune.attributions.get(observation__eleve=self.eleve))
        enregistrer_commune(utilisateur=self.enseignant, classe=self.classe, competence=a.competence,
            ids=[self.autre.pk], valeurs={"commentaire": "Texte modifié"}, commune=commune)
        trace.refresh_from_db()
        self.assertEqual(trace.commentaire, "Lou raconte")
        self.assertTrue(trace.reussite)
        supprimer_commune(utilisateur=self.enseignant, commune=commune)
        trace.refresh_from_db(); self.assertIsNone(trace.supprime_le)
        self.assertEqual(EleveApprentissage.objects.filter(active=True).count(), 2)

    def test_sous_domaine_et_changement_de_base_conservent_suivi(self):
        s = self.adoption.contenu["sous_domaines"][0]
        a = self.creer(sous_domaine_id=s["id"])
        self.adopter(self.b)
        c = next(c for d in arbre_competences(self.ecole, classe=self.classe) for c in d.visibles if c.pk == a.competence_id)
        self.assertEqual(c.sous_domaine.nom, s["nom"])
        self.assertEqual(Trace.objects.filter(observation__competence=a.competence).count(), 1)

    def test_droits_date_et_atomicite(self):
        for options in ({"utilisateur": self.direction}, {"date_observation": date(2000, 1, 1)},
                        {"adoption_attendue": 0}, {"sous_domaine_id": 999999}):
            with self.assertRaises((PermissionDenied, ValidationError)):
                self.creer(**options)
        self.assertFalse(CompetenceLocale.objects.exists())
        self.assertFalse(Trace.objects.exists())

    def test_pas_de_promotion_dans_referentiel_commun(self):
        from .services.ajouts_referentiels import proposer_ajout, catalogue_reprises
        a = self.creer()
        with self.assertRaises(PermissionDenied):
            proposer_ajout(utilisateur=self.direction, ecole=self.ecole, annee=self.classe.annee_scolaire, locale=a)
        self.assertNotIn(a, catalogue_reprises(utilisateur=self.enseignant, ecole=self.ecole,
            annee=self.classe.annee_scolaire, classe=self.classe))

    def test_retrait_de_disponibilite_conserve_historique(self):
        a = self.creer()
        associer(utilisateur=self.enseignant, classe=self.classe, locale=a,
            ids=[self.eleve.pk], adoption_attendue=self.adoption.pk, retirer=True)
        with self.assertRaises(PermissionDenied):
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=a.competence, statut=None)
        self.assertEqual(Trace.objects.count(), 1)

    def test_cloture_interdit_modification_portee(self):
        from .services.cloture_referentiels import clore
        a = self.creer()
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            clore(utilisateur=self.enseignant, classe=self.classe)
        with self.assertRaises(ValidationError):
            associer(utilisateur=self.enseignant, classe=self.classe, locale=a,
                ids=[self.autre.pk], adoption_attendue=self.adoption.pk)


class ParcoursLibre(Base):
    setUp = SuiviLibre.setUp
    adopter = SuiviLibre.adopter
    creer = SuiviLibre.creer

    def test_categories_vides_et_sous_domaines_visibles(self):
        self.client.force_login(self.enseignant)
        for nom, args in (("saisie_eleve", [self.eleve.pk]), ("choisir_competence", [self.classe.pk])):
            page = self.client.get(reverse(nom, args=args))
            self.assertContains(page, "Ajouter une réussite")
            self.assertContains(page, "Langage oral")
            self.assertContains(page, "Découverte de l’écrit")

    def test_formulaire_sans_javascript_et_selection_expresse(self):
        self.client.force_login(self.enseignant)
        url = reverse("ajouter_reussite", args=[self.classe.pk])
        page = self.client.get(url)
        d = dict(libelle="Je compose une suite fictive", domaine=self.entree["domaine_id"],
            eleves=[self.eleve.pk], niveau="PS", date_observation="2026-10-01",
            jeton=page.context["form"].initial["jeton"])
        reponse = self.client.post(url, d)
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(Trace.objects.get().reussite)
        self.assertEqual(EleveApprentissage.objects.count(), 1)
        self.assertFalse(Observation.objects.filter(eleve=self.autre).exists())

    def test_erreurs_rattachees_aux_champs_et_valeurs_conservees(self):
        self.client.force_login(self.enseignant)
        url = reverse("ajouter_reussite", args=[self.classe.pk])
        page = self.client.get(url)
        page = self.client.post(url, dict(libelle="Texte conservé", domaine=self.entree["domaine_id"],
            eleves=[self.eleve.pk], niveau="PS", date_observation="2000-01-01",
            jeton=page.context["form"].initial["jeton"]))
        self.assertIn("date_observation", page.context["form"].errors)
        self.assertContains(page, "Texte conservé")
        self.assertFalse(CompetenceLocale.objects.exists())

    def test_portee_individuelle_carnet_complet_et_collectif(self):
        a = self.creer()
        self.client.force_login(self.enseignant)
        self.assertContains(self.client.get(reverse("saisie_eleve", args=[self.eleve.pk])), a.competence.libelle)
        self.assertNotContains(self.client.get(reverse("saisie_eleve", args=[self.autre.pk])), a.competence.libelle)
        self.assertNotContains(self.client.get(reverse("carnet", args=[self.autre.pk]), {"contenu": "tout"}), a.competence.libelle)
        page = self.client.get(reverse("saisie_competence", args=[self.classe.pk, a.competence_id]))
        self.assertContains(page, "Hors du suivi")
        self.assertContains(page, "Ajouter des élèves")
        self.assertEqual(self.client.post(reverse("basculer", args=[self.autre.pk, a.competence_id])).status_code, 403)

    def test_association_sans_reussite_et_refus_direction(self):
        a = self.creer()
        self.client.force_login(self.enseignant)
        url = reverse("eleves_apprentissage", args=[self.classe.pk, a.pk])
        page = self.client.get(url)
        self.assertEqual(self.client.post(url, {"eleves": [self.autre.pk], "action": "ajouter",
            "jeton": page.context["form"].initial["jeton"]}).status_code, 302)
        self.assertFalse(Observation.objects.filter(eleve=self.autre).exists())
        self.client.force_login(self.direction)
        self.assertIn(self.client.get(url).status_code, (403, 404))

    def test_formulaire_perime_ne_cree_rien(self):
        self.client.force_login(self.enseignant)
        url = reverse("ajouter_reussite", args=[self.classe.pk])
        page = self.client.get(url)
        jeton = page.context["form"].initial["jeton"]
        self.adopter(self.b)
        page = self.client.post(url, dict(libelle="Essai périmé", domaine=self.entree["domaine_id"],
            eleves=[self.eleve.pk], niveau="PS", date_observation="2026-10-01", jeton=jeton))
        self.assertEqual(page.status_code, 200)
        self.assertFalse(CompetenceLocale.objects.exists())


class CarnetsLibres(Base):
    setUp = SuiviLibre.setUp
    adopter = SuiviLibre.adopter
    creer = SuiviLibre.creer

    def test_reussite_passee_reste_datee_apres_modification_etat(self):
        a = self.creer()
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=a.competence, statut="en_cours")
        self.client.force_login(self.enseignant)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "reussites"})
        self.assertContains(page, "Réussite observée le 1 octobre 2026")
        self.assertContains(page, "En cours d'apprentissage")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            pdf = self.client.get(reverse("carnet_pdf", args=[self.eleve.pk]), {"contenu": "reussites"})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        import shutil, subprocess
        if shutil.which("pdftotext"):
            texte = subprocess.run(["pdftotext", "-", "-"], input=pdf.content,
                                   capture_output=True, check=True).stdout.decode()
            self.assertIn("Je raconte ma construction", texte)
            self.assertIn("Réussite observée", texte)

    def test_masquage_et_cloture_conservent_le_carnet_et_le_sous_domaine(self):
        from .services.adaptations_referentiels import enregistrer_adaptation
        from .services.cloture_referentiels import clore
        a = self.creer(sous_domaine_id=self.adoption.contenu["sous_domaines"][0]["id"])
        enregistrer_adaptation(utilisateur=self.enseignant, ecole=self.ecole,
            annee=self.classe.annee_scolaire, classe=self.classe, adoption_attendue=self.adoption.pk,
            competence=a.competence, libelle="Je décris ma construction", visible=False, revision_attendue=0)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            clore(utilisateur=self.enseignant, classe=self.classe)
        self.client.force_login(self.enseignant)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]),
                               {"annee": self.classe.annee_scolaire, "sous_domaines": "1"})
        self.assertContains(page, "Je décris ma construction")
        self.assertContains(page, "Langage oral")
        self.assertContains(page, "Réussite observée")

    def test_statistique_limitee_aux_eleves_encore_suivis(self):
        from .statistiques import repartition_competences
        a = self.creer([self.eleve.pk, self.autre.pk])
        associer(utilisateur=self.enseignant, classe=self.classe, locale=a,
            ids=[self.autre.pk], adoption_attendue=self.adoption.pk, retirer=True)
        c = next(c for d in arbre_competences(self.ecole, classe=self.classe) for c in d.visibles if c.pk == a.competence_id)
        repartition_competences(self.classe, [c])
        self.assertEqual(c.repartition["total"], 1)
        self.assertEqual(c.repartition["reussites"], 1)

    def test_nouvelle_annee_ouvre_suivi_sans_nouvel_etat(self):
        from .models import Classe, ReferentielAnnuel
        a = self.creer()
        c = Classe.objects.create(ecole=self.ecole, nom="Suite fictive", annee_scolaire="2027-2028")
        self.affecter_enseignant(c); c.activer()
        enfant = Eleve.objects.create(ecole=self.ecole, prenom="Jade")
        Scolarite.objects.create(eleve=enfant, classe=c, annee_scolaire=c.annee_scolaire, niveau="PS")
        annuel = ReferentielAnnuel.objects.create(ecole=self.ecole, annee_scolaire=c.annee_scolaire, version_proposee=self.a)
        ad = AdoptionReferentiel.objects.create(classe=c, annuel=annuel, version=self.a, contenu=self.adoption.contenu)
        associer(utilisateur=self.enseignant, classe=c, locale=a, ids=[enfant.pk], adoption_attendue=ad.pk)
        self.assertFalse(Observation.objects.filter(eleve=enfant).exists())
        self.assertFalse(EtatAnnuelObservation.objects.filter(annee_scolaire=c.annee_scolaire).exists())
