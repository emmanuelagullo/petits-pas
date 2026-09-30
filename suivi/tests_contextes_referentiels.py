from datetime import date

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import AdoptionReferentiel, Classe, Competence, EtatAnnuelObservation
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import enregistrer_trace, modifier_etat
from .services.reprise_referentiels import reprendre
from .services.traces_communes import enregistrer_commune, personnaliser
from .tests import Base


class EcrituresAnnuelles(Base):
    def setUp(self):
        super().setUp()
        self.trace_initiale = self.creer_trace(commentaire="Avant la reprise")
        reprendre(self.ecole.pk)

    def test_modification_etat_renseigne_seulement_annee_courante(self):
        etat = EtatAnnuelObservation.objects.get(observation=self.trace_initiale.observation)
        self.assertFalse(etat.connu)
        observation = modifier_etat(utilisateur=self.enseignant, eleve=self.eleve,
                                    competence=self.competence, statut="en_cours")
        etat.refresh_from_db()
        self.assertTrue(etat.connu)
        self.assertEqual(etat.statut, "en_cours")
        self.assertEqual(etat.observation_id, observation.pk)
        self.assertEqual(etat.usage.adoption.classe_id, self.classe.pk)

    def test_trace_ne_transforme_pas_etat_inconnu_en_reussite(self):
        trace = enregistrer_trace(utilisateur=self.enseignant, eleve=self.eleve,
            competence=self.competence, scolarite=self.scolarite,
            valeurs={"commentaire": "Après", "date_observation": timezone.localdate()})
        self.assertEqual(trace.usage_referentiel.adoption.classe_id, self.classe.pk)
        self.assertFalse(EtatAnnuelObservation.objects.get(observation=trace.observation).connu)

    def test_correction_garde_contexte_apres_nouvelle_adoption(self):
        self.trace_initiale.refresh_from_db()
        usage_id = self.trace_initiale.usage_referentiel_id
        # L'autorisation reste celle de la classe actuelle : on simule seulement
        # une nouvelle adoption dans la classe pour vérifier le contexte ancien.
        ancienne = AdoptionReferentiel.objects.get(classe=self.classe)
        ancienne.courante = False
        ancienne.save()
        AdoptionReferentiel.objects.create(classe=self.classe, annuel=ancienne.annuel, version=ancienne.version)
        trace = enregistrer_trace(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence,
            scolarite=self.scolarite, trace=self.trace_initiale, valeurs={"commentaire": "Corrigé"})
        self.assertEqual(trace.usage_referentiel_id, usage_id)

    def test_commune_et_personnalisation_conservent_usage(self):
        commune = enregistrer_commune(utilisateur=self.enseignant, classe=self.classe,
            competence=self.competence, ids=[self.eleve.pk], valeurs={"date_observation": date(2026, 9, 29)})
        trace = commune.attributions.get()
        self.assertEqual(trace.usage_referentiel_id, commune.usage_referentiel_id)
        personnelle = personnaliser(utilisateur=self.enseignant, trace=trace)
        self.assertEqual(personnelle.usage_referentiel_id, commune.usage_referentiel_id)

    def test_ajout_direct_et_masquage_refuses(self):
        autre = Competence.objects.create(domaine=self.competence.domaine, code="NOUVEAU", libelle="Ajout direct")
        with self.assertRaises(PermissionDenied):
            usage_pour_saisie(self.classe, autre)
        self.competence.active = False
        self.competence.save()
        with self.assertRaises(PermissionDenied):
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")

    def test_nouvelle_classe_initialisee_sans_modifier_ancienne(self):
        autre = Classe.objects.create(ecole=self.ecole, nom="Lucioles", annee_scolaire="2027-2028")
        usage = usage_pour_saisie(autre, self.competence)
        self.assertEqual(usage.adoption.annuel.annee_scolaire, "2027-2028")
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=self.classe).count(), 1)
