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
        super().setUp()
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
