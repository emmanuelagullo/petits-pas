from io import StringIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from comptes.models import AffectationClasse
from .autorisations import GERER_REFERENTIEL_CLASSE, GERER_REFERENTIEL_ECOLE, MODIFIER_ETAT, autorise, classes_accessibles
from .models import AdoptionReferentiel, ChoixApplicationAnnuel, ChoixEcoleAnnuel, Ecole, EvenementAudit, VersionReferentiel
from .services.choix_bases_referentiels import choix_bases, enregistrer_choix_ecole, publier_choix_application
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class ChoixAnnuels(Base):
    def setUp(self):
        super().setUp()
        self.annee = self.classe.annee_scolaire
        self.creer_trace(commentaire="Trace conservée")
        reprendre(self.ecole.pk)
        self.a = importer(document("fictive-a"))[0]
        self.b = importer(document("fictive-b"))[0]

    def publier(self, ids=None, defaut=None, revision=0, annee=None):
        return publier_choix_application(annee=annee or self.annee,
            versions_ids=ids if ids is not None else [self.a.pk, self.b.pk],
            proposee_id=defaut if defaut is not None else self.a.pk, revision_attendue=revision)

    def regler(self, *, restreindre=False, ids=(), defaut=None, utilisateur=None, revisions=None):
        return enregistrer_choix_ecole(utilisateur=utilisateur or self.direction, ecole=self.ecole,
            annee=self.annee, restreindre=restreindre, versions_ids=ids, proposee_id=defaut,
            revisions_attendues=revisions or choix_bases(self.ecole, self.annee).revisions)

    def test_catalogue_importe_pas_autorise_automatiquement(self):
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual(len(choix.versions), 1)
        self.assertEqual(choix.proposee.source.ecole_id, self.ecole.pk)
        self.assertNotIn(self.a.pk, [v.pk for v in choix.versions])
        self.assertFalse(ChoixApplicationAnnuel.objects.exists())
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_defaut_distinct_des_bases_autorisees(self):
        self.publier()
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual({v.pk for v in choix.versions}, {self.a.pk, self.b.pk})
        self.assertEqual(choix.proposee.pk, self.a.pk)
        self.regler(defaut=self.b.pk)
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual({v.pk for v in choix.versions}, {self.a.pk, self.b.pk})
        self.assertEqual(choix.proposee.pk, self.b.pk)

    def test_restriction_ecole_et_retour_aux_choix_proposes(self):
        self.publier()
        self.regler(restreindre=True, ids=[self.b.pk], defaut=self.b.pk)
        self.assertEqual([v.pk for v in choix_bases(self.ecole, self.annee).versions], [self.b.pk])
        self.regler()
        choix = choix_bases(self.ecole, self.annee)
        self.assertEqual(len(choix.versions), 2)
        self.assertEqual(choix.proposee.pk, self.a.pk)
        self.assertEqual(EvenementAudit.objects.filter(action="referentiel.choix_ecole").count(), 2)

    def test_liste_ecole_explicite_ne_s_etend_pas_avec_application(self):
        self.publier(ids=[self.a.pk])
        self.regler(restreindre=True, ids=[self.a.pk])
        self.publier(revision=1)
        self.assertEqual([v.pk for v in choix_bases(self.ecole, self.annee).versions], [self.a.pk])

    def test_heritage_durant_annee_mais_annees_independantes(self):
        self.publier()
        self.regler()
        self.publier(defaut=self.b.pk, revision=1)
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.b.pk)
        autre_annee = "2024-2025" if self.annee != "2024-2025" else "2023-2024"
        self.publier(ids=[self.a.pk], annee=autre_annee)
        self.assertEqual(choix_bases(self.ecole, autre_annee).proposee.pk, self.a.pk)
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.b.pk)

    def test_retrait_ne_bascule_ni_adoption_ni_defaut_local(self):
        self.publier()
        self.regler(restreindre=True, ids=[self.a.pk, self.b.pk], defaut=self.b.pk)
        avant = list(AdoptionReferentiel.objects.values())
        self.publier(ids=[self.a.pk], revision=1)
        choix = choix_bases(self.ecole, self.annee)
        self.assertIsNone(choix.proposee)
        self.assertEqual([v.pk for v in choix.versions], [self.a.pk])
        self.assertTrue(any("aucun remplacement" in message for message in choix.avertissements))
        self.assertTrue(any("observations sont conservées" in message for message in choix.avertissements))
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)
        self.assertEqual(ChoixEcoleAnnuel.objects.get().version_proposee_id, self.b.pk)

    def test_une_ecole_ne_retrouve_pas_origine_locale_autre_ecole(self):
        autre = Ecole.objects.create(nom="Autre école fictive")
        choix = choix_bases(autre, self.annee)
        self.assertFalse(choix.versions)
        self.assertIsNone(choix.proposee)
        with self.assertRaises(PermissionDenied):
            enregistrer_choix_ecole(utilisateur=self.direction, ecole=autre, annee=self.annee,
                restreindre=False, versions_ids=[], proposee_id=None, revisions_attendues=(0, 0))

    def test_ecole_ne_peut_pas_autoriser_hors_application(self):
        self.publier(ids=[self.a.pk])
        with self.assertRaises(ValidationError):
            self.regler(restreindre=True, ids=[self.b.pk], defaut=self.b.pk)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_defaut_et_liste_incoherents_refuses(self):
        self.publier()
        for options in ({"restreindre": True, "ids": [self.b.pk]},
                        {"restreindre": True, "ids": [self.a.pk], "defaut": self.b.pk},
                        {"ids": [self.a.pk]}, {"defaut": 99999}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.regler(**options)
        self.assertFalse(ChoixEcoleAnnuel.objects.exists())

    def test_liste_vide_interdit_nouveaux_choix_sans_supprimer_adoptions(self):
        self.publier()
        avant = list(AdoptionReferentiel.objects.values())
        self.regler(restreindre=True, ids=[])
        choix = choix_bases(self.ecole, self.annee)
        self.assertFalse(choix.versions)
        self.assertIsNone(choix.proposee)
        self.assertEqual(list(AdoptionReferentiel.objects.values()), avant)

    def test_revisions_application_et_ecole_protegent_confirmation(self):
        self.publier()
        revisions = choix_bases(self.ecole, self.annee).revisions
        self.publier(revision=1)
        with self.assertRaises(ValidationError): self.regler(revisions=revisions)
        self.regler()
        revisions = choix_bases(self.ecole, self.annee).revisions
        self.regler(defaut=self.b.pk)
        with self.assertRaises(ValidationError): self.regler(revisions=revisions)
        with self.assertRaises(ValidationError): self.publier(revision=1)

    def test_application_refuse_source_locale_et_annee_invalide(self):
        locale = VersionReferentiel.objects.get(source__ecole=self.ecole, numero="initial")
        with self.assertRaises(ValidationError): self.publier(ids=[locale.pk], defaut=locale.pk)
        for annee in ("2026-2028", "2026", "abcd-efgh"):
            with self.subTest(annee=annee), self.assertRaises(ValidationError):
                self.publier(annee=annee)
        self.assertFalse(ChoixApplicationAnnuel.objects.exists())

    def test_droits_referentiels_distincts_de_saisie(self):
        self.assertTrue(autorise(self.direction, GERER_REFERENTIEL_ECOLE, self.ecole))
        self.assertTrue(autorise(self.direction, GERER_REFERENTIEL_CLASSE, self.classe))
        self.assertFalse(autorise(self.direction, MODIFIER_ETAT, self.classe))
        self.assertTrue(autorise(self.enseignant, GERER_REFERENTIEL_CLASSE, self.classe))
        self.assertFalse(autorise(self.enseignant, GERER_REFERENTIEL_ECOLE, self.ecole))
        self.assertIn(self.classe, classes_accessibles(self.direction, GERER_REFERENTIEL_CLASSE))
        with self.assertRaises(PermissionDenied): self.regler(utilisateur=self.enseignant)
        AffectationClasse.objects.filter(appartenance__utilisateur=self.enseignant, classe=self.classe).update(etat="terminee", date_fin=timezone.localdate())
        self.assertFalse(autorise(self.enseignant, GERER_REFERENTIEL_CLASSE, self.classe))

    def test_commande_consultation_sans_ecriture_et_publication(self):
        sortie = StringIO()
        call_command("proposer_bases_referentiels", annee=self.annee, stdout=sortie)
        self.assertIn("non publiés", sortie.getvalue())
        self.assertFalse(ChoixApplicationAnnuel.objects.exists())
        with self.assertRaises(CommandError):
            call_command("proposer_bases_referentiels", annee=self.annee, autoriser=[self.a.pk], defaut=self.a.pk)
        call_command("proposer_bases_referentiels", annee=self.annee, autoriser=[self.a.pk], defaut=self.a.pk,
            revision_attendue=0, stdout=StringIO())
        self.assertEqual(choix_bases(self.ecole, self.annee).proposee.pk, self.a.pk)
