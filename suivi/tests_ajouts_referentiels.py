from tempfile import TemporaryDirectory
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from .models import AdoptionReferentiel, Classe, CompetenceLocale, EtatAnnuelObservation, Observation
from .referentiels import contenu_adoption, contenu_origine
from .services.ajouts_referentiels import creer_ajout, proposer_ajout, reprendre_ajout
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.contextes_referentiels import usage_pour_saisie
from .services.cloture_referentiels import clore
from .services.pedagogie import modifier_etat
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
