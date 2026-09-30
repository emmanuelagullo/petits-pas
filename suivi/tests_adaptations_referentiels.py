from tempfile import TemporaryDirectory

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from .models import AdaptationCompetence, AdoptionReferentiel, Classe, Competence, Ecole, EtatAnnuelObservation, Observation, Trace
from .referentiels import arbre_competences, contenu_origine
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.cloture_referentiels import clore
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base


class AdaptationsAnnuelles(Base):
    def setUp(self):
        super().setUp()
        self.creer_trace(commentaire="Parcours fictif conservé")
        reprendre(self.ecole.pk)
        self.adoption = AdoptionReferentiel.objects.get(classe=self.classe, courante=True)
        self.annee = self.classe.annee_scolaire
        self.entrer()

    def regler(self, *, classe=None, libelle=None, visible=None, utilisateur=None, revision=None, **options):
        regle = AdaptationCompetence.objects.filter(ecole=self.ecole, annee_scolaire=self.annee,
                                                    classe=classe, competence=self.competence).first()
        return enregistrer_adaptation(utilisateur=utilisateur or (self.enseignant if classe else self.direction),
            ecole=self.ecole, annee=self.annee, competence=self.competence, classe=classe,
            libelle=libelle, visible=visible, meme_sens=True,
            revision_attendue=revision if revision is not None else (regle.revision if regle else 0),
            adoption_attendue=self.adoption.pk if classe else None, **options)

    def lire(self, classe=None, inclure=False):
        return [c for d in arbre_competences(self.ecole, classe=classe or self.classe,
            inclure_ids=[self.competence.pk] if inclure else []) for c in d.visibles]

    def test_heritage_independant_libelle_et_visibilite(self):
        self.regler(libelle="Je peux dire mon prénom", visible=False)
        self.assertFalse(self.lire())
        self.regler(classe=self.classe, visible=True)
        self.assertEqual(self.lire()[0].libelle, "Je peux dire mon prénom")
        self.regler(libelle="Je sais dire mon prénom", visible=False)
        self.assertEqual(self.lire()[0].libelle, "Je sais dire mon prénom")
        self.regler(classe=self.classe, libelle="Je me présente", visible=None)
        self.assertFalse(self.lire())
        self.assertEqual(self.lire(inclure=True)[0].libelle, "Je me présente")
        self.regler(classe=self.classe)
        self.assertEqual(self.lire(inclure=True)[0].libelle, "Je sais dire mon prénom")
        self.regler()
        self.assertEqual(self.lire()[0].libelle, self.competence.libelle)

    def test_masquer_refuse_future_saisie_sans_modifier_parcours(self):
        avant = {model: list(model.objects.values()) for model in (Observation, EtatAnnuelObservation, Trace)}
        self.regler(classe=self.classe, libelle="Je me présente", visible=False)
        with self.assertRaises(PermissionDenied):
            modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        for model, valeurs in avant.items():
            self.assertEqual(list(model.objects.values()), valeurs)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Je me présente")
        self.assertContains(page, "Parcours fictif conservé")
        self.regler(classe=self.classe, visible=True)
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        self.assertEqual(Observation.objects.get().competence_id, self.competence.pk)

    def test_demasquer_ancien_masquage_sans_recrire_catalogue(self):
        Competence.objects.filter(pk=self.competence.pk).update(active=False)
        self.assertFalse(self.lire())
        self.regler(classe=self.classe, visible=True)
        self.assertTrue(self.lire())
        self.assertEqual(usage_pour_saisie(self.classe, self.competence).competence_id, self.competence.pk)
        self.competence.refresh_from_db()
        self.assertFalse(self.competence.active)

    def test_sources_et_autres_annees_restent_intactes(self):
        origine = contenu_origine(self.adoption)
        self.regler(libelle="Je me présente", visible=False)
        self.assertEqual(contenu_origine(self.adoption), origine)
        self.competence.refresh_from_db()
        self.assertEqual(self.competence.libelle, "Je dis mon prénom")
        autre = Classe.objects.create(ecole=self.ecole, nom="Papillons", annee_scolaire="2024-2025")
        self.assertEqual(self.lire(classe=autre)[0].libelle, self.competence.libelle)

    def test_cloture_conserve_derniers_choix_et_ignore_heritage_futur(self):
        self.regler(libelle="Je me présente", visible=True)
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
        self.regler(libelle="Je peux dire mon prénom", visible=False)
        self.assertEqual(self.lire()[0].libelle, "Je me présente")
        self.assertEqual(finale.etat_final["contenu"]["competences"][0]["libelle"], "Je me présente")
        with self.assertRaises(ValidationError): self.regler(classe=self.classe, visible=False)

    def test_validation_droits_et_revisions(self):
        with self.assertRaises(PermissionDenied): self.regler(utilisateur=self.enseignant)
        self.regler(classe=self.classe, libelle="Je me présente")
        with self.assertRaises(ValidationError): self.regler(classe=self.classe, revision=0)
        for options in ({"libelle": " "}, {"libelle": "x" * 301}, {"visible": "oui"}):
            with self.subTest(options=options), self.assertRaises(ValidationError): self.regler(**options)
        with self.assertRaises(ValidationError):
            enregistrer_adaptation(utilisateur=self.direction, ecole=self.ecole, annee=self.annee,
                competence=self.competence, libelle="Un autre apprentissage", visible=None, revision_attendue=0)

    def test_contraintes_ecole_et_annee(self):
        autre = Ecole.objects.create(nom="École fictive des Lilas")
        for regle in (AdaptationCompetence(ecole=autre, annee_scolaire=self.annee, competence=self.competence),
                      AdaptationCompetence(ecole=self.ecole, annee_scolaire="2024-2025", competence=self.competence, classe=self.classe)):
            with self.assertRaises(ValidationError): regle.full_clean()
