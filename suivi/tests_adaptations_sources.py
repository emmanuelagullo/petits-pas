from django.core.exceptions import PermissionDenied

from .models import AdaptationCompetence, Observation
from .referentiels import contenu_adoption, contenu_origine
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.adoption_bases_referentiels import adopter_base, apercu_adoption
from .services.choix_bases_referentiels import publier_choix_application
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class AdaptationsSources(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        self.a = importer(document())[0]
        self.b = importer(document("autre-source-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.adoption = self.adopter(self.a)
        self.competence = self.adoption.usages.get().competence

    def adopter(self, version):
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk)
        if apercu["garde"]["niveau"] == "rouge" and not apercu["meme"]:
            from .fixtures_garde_fous import ouvrir_exception_fictive
            ouvrir_exception_fictive(self.classe)
            apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk)
        return adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"],
            garde_attendue=apercu["garde"]["empreinte"])

    def regler(self, *, libelle=None, visible=None, revision=0):
        return enregistrer_adaptation(utilisateur=self.enseignant, ecole=self.ecole,
            annee=self.classe.annee_scolaire, classe=self.classe, competence=self.competence,
            libelle=libelle, visible=visible, revision_attendue=revision,
            adoption_attendue=self.adoption.pk)

    def test_nouvelle_version_garde_adaptation_et_origine_distincte(self):
        self.regler(libelle="Je m'exprime")
        doc = document(version="2")
        doc["domaines"][0]["competences"][0].update(libelle="Je prends la parole", code="NOUVEAU-CODE")
        deux = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk, deux.pk],
            proposee_id=deux.pk, revision_attendue=1)
        adoption = self.adopter(deux)
        self.assertEqual(adoption.usages.get().competence_id, self.competence.pk)
        self.assertEqual(contenu_adoption(adoption)["competences"][0]["libelle"], "Je m'exprime")
        self.assertEqual(contenu_origine(adoption)["competences"][0]["libelle"], "Je prends la parole")
        self.assertEqual(contenu_origine(self.adoption)["competences"][0]["libelle"], "Je parle")
        self.assertEqual(AdaptationCompetence.objects.count(), 1)

    def test_meme_code_autre_source_ne_recoit_ni_adaptation_ni_reussite(self):
        self.regler(libelle="Je m'exprime", visible=False)
        autre = self.adopter(self.b)
        self.assertNotEqual(autre.usages.get().competence_id, self.competence.pk)
        self.assertEqual(contenu_adoption(autre)["competences"][0]["libelle"], "Je parle")
        self.assertTrue(contenu_adoption(autre)["competences"][0]["active"])
        self.assertFalse(Observation.objects.exists())

    def test_demasquer_hors_base_ne_permet_pas_saisie_et_retour_retrouve_etat(self):
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=self.competence, statut="reussi")
        self.adoption = self.adopter(self.b)
        self.regler(libelle="Je m'exprime", visible=True)
        with self.assertRaises(PermissionDenied): usage_pour_saisie(self.classe, self.competence)
        retour = self.adopter(self.a)
        self.assertEqual(contenu_adoption(retour)["competences"][0]["libelle"], "Je m'exprime")
        self.assertEqual(Observation.objects.get(competence=self.competence).statut, "reussi")
