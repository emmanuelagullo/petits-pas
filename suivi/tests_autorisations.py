import datetime
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from comptes.models import AffectationClasse, AppartenanceEcole, ResponsabiliteEcole

from .autorisations import (
    ACCEDER_APPLICATION,
    CONTRIBUER,
    GERER_CLASSE,
    MODIFIER_ETAT,
    VOIR_CLASSE,
    VOIR_SUIVI,
    affectation_active,
    appartenance_active,
    autorise,
    charger_classe_autorisee,
    classes_accessibles,
    peut_activer_classe,
    peut_auto_attribuer_temporairement,
    peut_suspendre_urgence,
    peut_terminer_affectation,
    toutes_autorisees,
)
from .models import (
    AccesParcoursEleve,
    Bilan,
    Classe,
    Competence,
    DemandeRapprochementEleve,
    Domaine,
    Ecole,
    Eleve,
    EvenementAudit,
    Observation,
    Scolarite,
    Trace,
)


class PolitiqueAutorisations(TestCase):
    def setUp(self):
        self.aujourdhui = timezone.localdate()
        self.ecole_a = Ecole.objects.create(nom="École A")
        self.ecole_b = Ecole.objects.create(nom="École B")
        self.a1 = Classe.objects.create(ecole=self.ecole_a, nom="A1")
        self.a3 = Classe.objects.create(ecole=self.ecole_a, nom="A3")
        self.b1 = Classe.objects.create(ecole=self.ecole_b, nom="B1")
        self.remi, self.remi_a = self._membre("remi", self.ecole_a)
        self.amina, self.amina_a = self._membre("amina", self.ecole_a)
        self.cora, self.cora_a = self._membre("cora", self.ecole_a)
        self.diane, self.diane_a = self._membre("diane", self.ecole_a)
        self.bruno, self.bruno_b = self._membre("bruno", self.ecole_b)
        self.multi, self.multi_a = self._membre("multi", self.ecole_a)
        self.multi_b = AppartenanceEcole.objects.create(
            utilisateur=self.multi, ecole=self.ecole_b
        )
        ResponsabiliteEcole.objects.create(appartenance=self.diane_a)
        self.affectation_remi = self._affecter(
            self.remi_a, self.a1, AffectationClasse.RESPONSABLE
        )
        self._affecter(
            self.amina_a, self.a1, AffectationClasse.ENSEIGNANT_ASSOCIE
        )
        self._affecter(
            self.cora_a, self.a1, AffectationClasse.CONTRIBUTEUR
        )
        self._affecter(
            self.bruno_b, self.b1, AffectationClasse.RESPONSABLE
        )
        self._affecter(
            self.multi_a, self.a1, AffectationClasse.ENSEIGNANT_ASSOCIE
        )
        self._affecter(
            self.multi_b, self.b1, AffectationClasse.ENSEIGNANT_ASSOCIE
        )
        self.a1.activer()
        self.b1.activer()

    def _membre(self, nom, ecole):
        utilisateur = get_user_model().objects.create_user(nom)
        appartenance = AppartenanceEcole.objects.create(
            utilisateur=utilisateur, ecole=ecole
        )
        return utilisateur, appartenance

    def _affecter(self, appartenance, classe, type, **champs):
        return AffectationClasse.objects.create(
            appartenance=appartenance, classe=classe, type=type, **champs
        )

    def test_t002_compte_desactive_est_refuse(self):
        self.remi.is_active = False
        self.remi.save(update_fields=["is_active"])
        self.assertFalse(autorise(self.remi, VOIR_SUIVI, self.a1))

    def test_t003_appartenance_terminee_est_refusee(self):
        self.remi_a.etat = AppartenanceEcole.TERMINEE
        self.remi_a.save(update_fields=["etat"])
        self.assertIsNone(appartenance_active(self.remi, self.ecole_a))
        self.assertFalse(autorise(self.remi, ACCEDER_APPLICATION, ecole=self.ecole_a))

    def test_t004_t005_t006_bornes_temporelles(self):
        utilisateur, appartenance = self._membre("temporaire", self.ecole_a)
        self._affecter(
            appartenance,
            self.a1,
            AffectationClasse.RESPONSABLE,
            date_debut=self.aujourdhui - datetime.timedelta(days=3),
            date_fin=self.aujourdhui - datetime.timedelta(days=1),
        )
        debut = self.aujourdhui + datetime.timedelta(days=1)
        self._affecter(
            appartenance,
            self.a1,
            AffectationClasse.RESPONSABLE,
            date_debut=debut,
        )
        self.assertIsNone(affectation_active(utilisateur, self.a1))
        self.assertFalse(autorise(utilisateur, VOIR_SUIVI, self.a1))
        self.assertIsNotNone(affectation_active(utilisateur, self.a1, date=debut))

    def test_t010_et_t013_isolation_inter_ecoles(self):
        self.assertFalse(autorise(self.remi, VOIR_SUIVI, self.b1))
        with self.assertRaises(Http404):
            charger_classe_autorisee(self.remi, self.b1.pk, VOIR_SUIVI)
        self.assertTrue(autorise(self.multi, VOIR_SUIVI, self.b1))
        self.assertFalse(
            autorise(self.multi, VOIR_SUIVI, self.b1, ecole=self.ecole_a)
        )

    def test_t014_lot_inter_ecoles_est_refuse(self):
        self.assertFalse(
            toutes_autorisees(
                self.remi, CONTRIBUER, [self.a1, self.b1], ecole=self.ecole_a
            )
        )

    def test_t020_direction_sans_acces_pedagogique(self):
        self.assertTrue(autorise(self.diane, GERER_CLASSE, self.a1))
        self.assertFalse(autorise(self.diane, VOIR_SUIVI, self.a1))
        self.assertFalse(autorise(self.diane, MODIFIER_ETAT, self.a1))

    def test_t022_t023_auto_attribution_temporaire(self):
        fin = self.aujourdhui + datetime.timedelta(days=10)
        self.assertFalse(
            peut_auto_attribuer_temporairement(self.diane, self.a1, "", fin)
        )
        self.assertFalse(
            peut_auto_attribuer_temporairement(self.diane, self.a1, "Motif", None)
        )
        self.assertTrue(
            peut_auto_attribuer_temporairement(self.diane, self.a1, "Motif", fin)
        )

    def test_t024_t025_affectation_temporaire_de_direction(self):
        fin = self.aujourdhui + datetime.timedelta(days=1)
        self._affecter(
            self.diane_a,
            self.a1,
            AffectationClasse.RESPONSABLE,
            date_fin=fin,
            motif="Continuité",
        )
        self.assertTrue(autorise(self.diane, VOIR_SUIVI, self.a1))
        self.assertFalse(
            autorise(
                self.diane,
                VOIR_SUIVI,
                self.a1,
                date=fin + datetime.timedelta(days=1),
            )
        )

    def test_t030_t031_t032_activation_de_classe(self):
        self.assertEqual(self.a3.etat, Classe.PREPARATION)
        self.assertFalse(peut_activer_classe(self.diane, self.a3))
        self._affecter(
            self.remi_a, self.a3, AffectationClasse.RESPONSABLE
        )
        self.assertTrue(peut_activer_classe(self.diane, self.a3))

    def test_t033_t034_dernier_responsable_et_remplacement(self):
        self.assertFalse(
            peut_terminer_affectation(self.diane, self.affectation_remi)
        )
        _, appartenance = self._membre("remplacant", self.ecole_a)
        remplacement = self._affecter(
            appartenance, self.a1, AffectationClasse.RESPONSABLE
        )
        self.assertTrue(
            peut_terminer_affectation(
                self.diane, self.affectation_remi, remplacement
            )
        )

    def test_t035_suspension_urgente_possible(self):
        self.assertTrue(peut_suspendre_urgence(self.diane, self.affectation_remi))

    def test_t036_niveaux_simultanes_refuses(self):
        with self.assertRaises(ValidationError):
            self._affecter(
                self.amina_a, self.a1, AffectationClasse.CONTRIBUTEUR
            )

    def test_refus_par_defaut_et_selecteurs(self):
        self.assertFalse(autorise(self.remi, "inconnue", self.a1))
        self.assertQuerySetEqual(
            classes_accessibles(self.remi, VOIR_SUIVI), [self.a1]
        )
        self.assertNotIn(self.b1, classes_accessibles(self.remi, VOIR_CLASSE))


class LecturesCloisonnees(PolitiqueAutorisations):
    def setUp(self):
        super().setUp()
        self.alice = self._eleve("Alice", "Dupont", "PS", self.a1)
        self.alex_martin = self._eleve("Alex", "Martin", "MS", self.a1)
        self.alex_moreau = self._eleve("Alex", "Moreau", "MS", self.a1)
        self.domaine = Domaine.objects.create(
            ecole=self.ecole_a, code="LANG", nom="Langage"
        )
        self.competence = Competence.objects.create(
            domaine=self.domaine,
            code="LANG-1",
            libelle="S'exprimer",
            niveau="PS",
        )

    def _eleve(self, prenom, nom, niveau, classe):
        eleve = Eleve.objects.create(
            ecole=classe.ecole, prenom=prenom, nom=nom
        )
        Scolarite.objects.create(
            eleve=eleve,
            classe=classe,
            annee_scolaire=classe.annee_scolaire,
            niveau=niveau,
        )
        return eleve

    def test_t040_contributeur_ne_voit_que_identite_minimale(self):
        self.client.force_login(self.cora)

        reponse = self.client.get(f"/classe/{self.a1.pk}/")

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Alice D.")
        self.assertNotContains(reponse, "Alice Dupont")
        self.assertNotContains(reponse, "réussite")

    def test_t041_homonymes_affichent_le_nom_complet(self):
        self.client.force_login(self.cora)

        reponse = self.client.get(f"/classe/{self.a1.pk}/")

        self.assertContains(reponse, "Alex Martin")
        self.assertContains(reponse, "Alex Moreau")

    def test_t042_t043_contributeur_ne_voit_pas_le_suivi(self):
        observation = Observation.objects.create(
            eleve=self.alice,
            competence=self.competence,
        )
        trace_amina = Trace.objects.create(
            observation=observation,
            scolarite=self.alice.scolarite_courante(),
            auteur=self.amina,
            dernier_editeur=self.amina,
            commentaire="Trace d'Amina",
        )
        self.client.force_login(self.cora)

        suivi = self.client.get(f"/eleve/{self.alice.pk}/")
        trace = self.client.get(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace_amina.pk}/"
        )

        self.assertEqual(suivi.status_code, 404)
        self.assertEqual(trace.status_code, 404)
        self.assertTrue(Observation.objects.filter(pk=observation.pk).exists())

    def test_t060_responsable_modifie_etat_et_audit(self):
        self.client.force_login(self.remi)

        reponse = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/basculer/"
        )

        self.assertEqual(reponse.status_code, 200)
        observation = Observation.objects.get(
            eleve=self.alice, competence=self.competence
        )
        evenement = EvenementAudit.objects.get(action="observation.etat_modifie")
        self.assertEqual(observation.statut, Observation.REUSSI)
        self.assertEqual(evenement.acteur, self.remi)
        self.assertEqual(evenement.anciennes_valeurs, {"statut": None})

    def test_t061_associe_ne_modifie_pas_etat(self):
        self.client.force_login(self.amina)

        reponse = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/basculer/"
        )

        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(Observation.objects.exists())

    def _ajouter_trace(self, utilisateur, commentaire="Une contribution"):
        self.client.force_login(utilisateur)
        return self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/trace/",
            {
                "commentaire": commentaire,
                "date_observation": self.aujourdhui.isoformat(),
                "visible_carnet": "on",
            },
        )

    def test_t062_associe_ajoute_trace_sans_fixer_etat(self):
        reponse = self._ajouter_trace(self.amina)

        self.assertEqual(reponse.status_code, 302)
        trace = Trace.objects.get()
        self.assertEqual(trace.auteur, self.amina)
        self.assertEqual(trace.dernier_editeur, self.amina)
        self.assertIsNone(trace.observation.statut)
        self.assertTrue(EvenementAudit.objects.filter(action="trace.creee").exists())

    def test_t063_t064_contributeur_ajoute_sans_voir_statut(self):
        reponse = self._ajouter_trace(self.cora, "Photo commentée")

        self.assertEqual(reponse.status_code, 302)
        trace = Trace.objects.get()
        self.assertEqual(trace.auteur, self.cora)
        self.assertIsNone(trace.observation.statut)
        page = self.client.get(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/trace/"
        )
        self.assertContains(page, "Photo commentée")
        self.assertNotContains(page, "Réussi")

    def test_t065_t067_auteur_et_editeur_restent_distincts(self):
        self._ajouter_trace(self.cora, "Avant")
        trace = Trace.objects.get()
        self.client.force_login(self.remi)

        reponse = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace.pk}/",
            {
                "commentaire": "Après",
                "date_observation": self.aujourdhui.isoformat(),
                "visible_carnet": "on",
            },
        )

        self.assertEqual(reponse.status_code, 302)
        trace.refresh_from_db()
        self.assertEqual(trace.auteur, self.cora)
        self.assertEqual(trace.dernier_editeur, self.remi)
        evenement = EvenementAudit.objects.get(action="trace.modifiee")
        self.assertEqual(evenement.anciennes_valeurs["commentaire"], "Avant")

    def test_t066_auteur_ne_corrige_plus_apres_affectation(self):
        self._ajouter_trace(self.cora)
        trace = Trace.objects.get()
        affectation = AffectationClasse.objects.get(
            appartenance=self.cora_a, classe=self.a1
        )
        affectation.etat = AffectationClasse.TERMINEE
        affectation.save(update_fields=["etat"])

        reponse = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace.pk}/",
            {"commentaire": "Interdit"},
        )

        self.assertEqual(reponse.status_code, 403)
        trace.refresh_from_db()
        self.assertEqual(trace.commentaire, "Une contribution")

    def test_t068_associe_ne_modifie_pas_trace_autrui(self):
        self._ajouter_trace(self.cora)
        trace = Trace.objects.get()
        self.client.force_login(self.amina)

        reponse = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace.pk}/",
            {"commentaire": "Interdit"},
        )

        self.assertEqual(reponse.status_code, 404)

    def test_t069_suppression_logique_et_restauration(self):
        self._ajouter_trace(self.cora)
        trace = Trace.objects.get()
        self.client.force_login(self.remi)

        suppression = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace.pk}/supprimer/"
        )
        trace.refresh_from_db()
        self.assertEqual(suppression.status_code, 302)
        self.assertIsNotNone(trace.supprime_le)

        restauration = self.client.post(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/"
            f"trace/{trace.pk}/restaurer/"
        )
        trace.refresh_from_db()
        self.assertEqual(restauration.status_code, 302)
        self.assertIsNone(trace.supprime_le)
        self.assertQuerySetEqual(
            EvenementAudit.objects.filter(
                action__in=["trace.supprimee", "trace.restauree"]
            ).order_by("cree_le"),
            ["trace.supprimee", "trace.restauree"],
            transform=lambda evenement: evenement.action,
        )

    def test_t044_associe_voit_le_suivi_complet(self):
        self.client.force_login(self.amina)

        reponse = self.client.get(f"/eleve/{self.alice.pk}/")

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "S&#x27;exprimer")

    def test_t045_associe_ne_voit_pas_une_autre_classe(self):
        autre_responsable, appartenance = self._membre("autre", self.ecole_a)
        a2 = Classe.objects.create(ecole=self.ecole_a, nom="A2")
        self._affecter(appartenance, a2, AffectationClasse.RESPONSABLE)
        a2.activer()
        autre_eleve = self._eleve("Zoé", "Durand", "GS", a2)
        self.client.force_login(self.amina)

        self.assertEqual(self.client.get(f"/classe/{a2.pk}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/eleve/{autre_eleve.pk}/").status_code,
            404,
        )
        self.assertTrue(autre_responsable.is_active)

    def test_direction_seule_ne_voit_pas_le_contenu_pedagogique(self):
        self.client.force_login(self.diane)

        self.assertEqual(self.client.get(f"/classe/{self.a1.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/eleve/{self.alice.pk}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/eleve/{self.alice.pk}/carnet/").status_code,
            404,
        )

    def test_ouvrir_formulaire_trace_ne_cree_pas_observation(self):
        self.client.force_login(self.amina)

        reponse = self.client.get(
            f"/eleve/{self.alice.pk}/competence/{self.competence.pk}/trace/"
        )

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(
            Observation.objects.filter(
                eleve=self.alice, competence=self.competence
            ).exists()
        )

    def test_accueil_est_limite_aux_classes_accessibles(self):
        self.client.force_login(self.amina)

        reponse = self.client.get("/")

        self.assertContains(reponse, "A1")
        self.assertNotContains(reponse, "B1")


class AdministrationCouranteEleves(LecturesCloisonnees):
    def _ancien_dossier(self, suffixe=""):
        ancienne_classe = Classe.objects.create(
            ecole=self.ecole_a,
            nom=f"Ancienne classe{suffixe}",
            annee_scolaire="2025-2026",
        )
        eleve = Eleve.objects.create(
            ecole=self.ecole_a,
            prenom="Lina",
            nom="Martin",
            annee_naissance=2021,
        )
        scolarite = Scolarite.objects.create(
            eleve=eleve,
            classe=ancienne_classe,
            annee_scolaire="2025-2026",
            niveau="PS",
        )
        observation = Observation.objects.create(
            eleve=eleve,
            competence=self.competence,
            statut=Observation.REUSSI,
            date_observation=datetime.date(2026, 5, 10),
        )
        trace_publique = Trace.objects.create(
            observation=observation,
            scolarite=scolarite,
            date_observation=datetime.date(2026, 5, 10),
            commentaire="Acquisition antérieure publiée",
            visible_carnet=True,
            auteur=self.remi,
        )
        trace_interne = Trace.objects.create(
            observation=observation,
            scolarite=scolarite,
            date_observation=datetime.date(2026, 5, 11),
            commentaire="Note interne ancienne",
            visible_carnet=False,
            auteur=self.remi,
        )
        Bilan.objects.create(
            scolarite=scolarite,
            date_bilan=datetime.date(2026, 6, 20),
            texte="Bilan final antérieur",
            visible_carnet=True,
            auteur=self.remi,
        )
        return eleve, trace_publique, trace_interne

    def _demander_rapprochement(self):
        eleve, trace_publique, trace_interne = self._ancien_dossier()
        self.client.force_login(self.remi)
        reponse = self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {"liste": "Lina ; Martin ; MS ; 2021", "niveau": "MS"},
        )
        demande = DemandeRapprochementEleve.objects.get()
        return eleve, trace_publique, trace_interne, demande, reponse

    def test_t050_t051_responsable_cree_et_importe_nouveaux_eleves(self):
        self.client.force_login(self.remi)

        reponse = self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {
                "liste": "Nora ; Petit ; PS ; 2022\nYanis ; Roux ; MS ; 2021",
                "niveau": "PS",
            },
        )

        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(self.a1.eleves.filter(prenom="Nora").exists())
        self.assertTrue(self.a1.eleves.filter(prenom="Yanis").exists())
        self.assertEqual(
            EvenementAudit.objects.filter(action="eleve.cree").count(), 2
        )

    def test_t052_correspondance_cree_demande_sans_liaison(self):
        eleve, _, _, demande, reponse = self._demander_rapprochement()

        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(Eleve.objects.filter(prenom="Lina").count(), 1)
        self.assertFalse(eleve.scolarites.filter(classe=self.a1).exists())
        self.assertEqual(demande.etat, DemandeRapprochementEleve.EN_ATTENTE)
        self.assertTrue(
            EvenementAudit.objects.filter(action="rapprochement.demande").exists()
        )

    def test_t053_responsable_ne_valide_pas_rapprochement(self):
        eleve, _, _, demande, _ = self._demander_rapprochement()

        reponse = self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {
                "action": "valider_rapprochement",
                "demande": demande.pk,
                "eleve": eleve.pk,
            },
        )

        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(AccesParcoursEleve.objects.exists())

    def test_t054_t056_direction_valide_et_ouvre_passe_publie(self):
        eleve, _, _, demande, _ = self._demander_rapprochement()
        self.client.force_login(self.diane)

        validation = self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {
                "action": "valider_rapprochement",
                "demande": demande.pk,
                "eleve": eleve.pk,
            },
        )

        self.assertEqual(validation.status_code, 302)
        self.assertTrue(AccesParcoursEleve.objects.filter(eleve=eleve).exists())
        self.assertTrue(eleve.scolarites.filter(classe=self.a1).exists())
        self.client.force_login(self.remi)
        carnet = self.client.get(f"/eleve/{eleve.pk}/carnet/")
        self.assertContains(carnet, "Acquisition antérieure publiée")
        self.assertContains(carnet, "Bilan final antérieur")
        self.assertTrue(
            EvenementAudit.objects.filter(action="rapprochement.valide").exists()
        )

    def test_t055_demande_non_validee_ne_donne_aucun_acces(self):
        eleve, _, _, _, _ = self._demander_rapprochement()

        reponse = self.client.get(f"/eleve/{eleve.pk}/carnet/")

        self.assertEqual(reponse.status_code, 404)

    def test_t057_passe_interne_reste_inaccessible(self):
        eleve, _, trace_interne, demande, _ = self._demander_rapprochement()
        self.client.force_login(self.diane)
        self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {
                "action": "valider_rapprochement",
                "demande": demande.pk,
                "eleve": eleve.pk,
            },
        )
        self.client.force_login(self.remi)

        carnet = self.client.get(f"/eleve/{eleve.pk}/carnet/")
        trace = self.client.get(
            f"/eleve/{eleve.pk}/competence/{self.competence.pk}/"
            f"trace/{trace_interne.pk}/"
        )

        self.assertNotContains(carnet, "Note interne ancienne")
        self.assertEqual(trace.status_code, 404)

    def test_t058_homonymes_ne_sont_jamais_fusionnes(self):
        premier, _, _ = self._ancien_dossier(" 1")
        second = Eleve.objects.create(
            ecole=self.ecole_a,
            prenom=premier.prenom,
            nom=premier.nom,
            annee_naissance=premier.annee_naissance,
        )
        self.client.force_login(self.remi)

        self.client.post(
            f"/gestion/classe/{self.a1.pk}/eleves/",
            {"liste": "Lina ; Martin ; MS ; 2021", "niveau": "MS"},
        )

        self.assertEqual(Eleve.objects.filter(prenom="Lina").count(), 2)
        self.assertEqual(DemandeRapprochementEleve.objects.count(), 1)
        self.assertFalse(AccesParcoursEleve.objects.exists())
        self.assertFalse(second.scolarites.filter(classe=self.a1).exists())

    def _trace_photo(self, auteur):
        observation = Observation.objects.create(
            eleve=self.alice,
            competence=self.competence,
            statut=Observation.REUSSI,
        )
        return Trace.objects.create(
            observation=observation,
            scolarite=self.alice.scolarite_courante(),
            auteur=auteur,
            dernier_editeur=auteur,
            photo="traces/original-test.jpg",
            commentaire="Une photo",
        )

    def test_t070_associe_previsualise_sans_audit(self):
        self.client.force_login(self.amina)

        reponse = self.client.get(f"/eleve/{self.alice.pk}/carnet/")

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(EvenementAudit.objects.exists())
        self.assertNotContains(reponse, "Télécharger le PDF")

    def test_t071_associe_ne_genere_pas_pdf_ni_zip(self):
        self.client.force_login(self.amina)

        pdf = self.client.get(f"/eleve/{self.alice.pk}/carnet.pdf")
        archive = self.client.post(
            f"/classe/{self.a1.pk}/edition/", {"eleves": [self.alice.pk]}
        )

        self.assertEqual(pdf.status_code, 404)
        self.assertEqual(archive.status_code, 404)
        self.assertFalse(EvenementAudit.objects.exists())

    @patch("suivi.views._generer_pdf", return_value=b"%PDF-factice")
    def test_t072_t073_responsable_genere_et_telecharge_pdf(self, _generer):
        self.client.force_login(self.remi)

        reponse = self.client.get(f"/eleve/{self.alice.pk}/carnet.pdf")

        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(
            EvenementAudit.objects.filter(action="pdf.carnet_genere").exists()
        )
        self.assertTrue(
            EvenementAudit.objects.filter(
                action="pdf.carnet_telecharge"
            ).exists()
        )

    def test_t074_contributeur_ne_previsualise_pas_carnet(self):
        self.client.force_login(self.cora)

        reponse = self.client.get(f"/eleve/{self.alice.pk}/carnet/")

        self.assertEqual(reponse.status_code, 404)

    @patch("suivi.views.default_storage.open", return_value=BytesIO(b"image"))
    def test_t075_affichage_ordinaire_media_n_est_pas_audite(self, _ouvrir):
        trace = self._trace_photo(self.cora)
        self.client.force_login(self.remi)

        reponse = self.client.get(f"/media/trace/{trace.pk}/")
        contenu = b"".join(reponse.streaming_content)
        cle_devinee = self.client.get("/media/traces/original-test.jpg")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(contenu, b"image")
        self.assertEqual(cle_devinee.status_code, 404)
        self.assertFalse(
            EvenementAudit.objects.filter(
                action="media.original_telecharge"
            ).exists()
        )

    @patch("suivi.views.default_storage.size", return_value=5)
    @patch("suivi.views.default_storage.open", return_value=BytesIO(b"image"))
    def test_t076_responsable_telecharge_original_et_audit(
        self, _ouvrir, _taille
    ):
        trace = self._trace_photo(self.cora)
        self.client.force_login(self.remi)

        reponse = self.client.get(f"/media/trace/{trace.pk}/original/")
        contenu = b"".join(reponse.streaming_content)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(contenu, b"image")
        evenement = EvenementAudit.objects.get(
            action="media.original_telecharge"
        )
        self.assertEqual(evenement.objet_id, str(trace.pk))
        self.assertNotIn("contenu", evenement.nouvelles_valeurs)

    @patch("suivi.views.default_storage.size", return_value=5)
    @patch("suivi.views.default_storage.open", return_value=BytesIO(b"image"))
    def test_t077_contributeur_telecharge_sa_photo(self, _ouvrir, _taille):
        trace = self._trace_photo(self.cora)
        self.client.force_login(self.cora)

        reponse = self.client.get(f"/media/trace/{trace.pk}/original/")
        contenu = b"".join(reponse.streaming_content)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(contenu, b"image")
        self.assertTrue(
            EvenementAudit.objects.filter(
                action="media.original_telecharge", acteur=self.cora
            ).exists()
        )

    def test_t078_contributeur_ne_telecharge_pas_photo_autrui(self):
        trace = self._trace_photo(self.amina)
        self.client.force_login(self.cora)

        affichage = self.client.get(f"/media/trace/{trace.pk}/")
        original = self.client.get(f"/media/trace/{trace.pk}/original/")

        self.assertEqual(affichage.status_code, 404)
        self.assertEqual(original.status_code, 404)
        self.assertFalse(EvenementAudit.objects.exists())

    def test_ancienne_url_applicative_est_refusee_apres_fin_affectation(self):
        trace = self._trace_photo(self.cora)
        affectation = AffectationClasse.objects.get(
            appartenance=self.cora_a, classe=self.a1
        )
        affectation.etat = AffectationClasse.TERMINEE
        affectation.save(update_fields=["etat"])
        self.client.force_login(self.cora)

        reponse = self.client.get(f"/media/trace/{trace.pk}/")

        self.assertEqual(reponse.status_code, 403)
