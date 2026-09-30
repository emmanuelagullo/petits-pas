from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from .models import AdoptionReferentiel, Classe, Competence, EtatAnnuelObservation, Observation, Trace, VersionSourceEcole
from .presentation import illustration_effective, propositions
from .referentiels import arbre_competences
from .services.adoption_bases_referentiels import apercu_adoption, adopter_base
from .services.choix_bases_referentiels import publier_choix_application
from .services.cloture_referentiels import clore
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import modifier_etat
from .services.reprise_referentiels import reprendre
from .tests import Base
from .tests_import_sources_referentiels import document, importer


class AdoptionBases(Base):
    def setUp(self):
        super().setUp()
        reprendre(self.ecole.pk)
        doc = document()
        doc["domaines"][0]["competences"][0].update(icone="parler", formulations=[{"code": "p1", "texte": "<prénom> prend la parole."}])
        self.a = importer(doc)[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, self.b.pk],
            proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    def adopter(self, version=None):
        version = version or self.a
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk)
        return adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=version.pk,
            revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"])

    def test_apercu_sans_ecriture_puis_identites_et_contexte(self):
        nombre = Competence.objects.count()
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk)
        self.assertEqual(apercu["communes"], 0)
        self.assertEqual(Competence.objects.count(), nombre)
        self.assertFalse(VersionSourceEcole.objects.exists())
        adoption = self.adopter()
        competence = Competence.objects.get(pk=adoption.contenu["competences"][0]["id"])
        self.assertTrue(adoption.usages.get().cle_definition.startswith("source-"))
        self.assertEqual(arbre_competences(self.ecole, classe=self.classe)[0].visibles[0].libelle, "Je parle")
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        self.assertEqual(EtatAnnuelObservation.objects.get().usage.adoption_id, adoption.pk)
        with self.assertRaises(PermissionDenied): usage_pour_saisie(self.classe, self.competence)

    def test_deux_bases_sans_assimilation_et_retour_sans_doublon(self):
        a = self.adopter()
        b = self.adopter(self.b)
        retour = self.adopter()
        self.assertNotEqual(a.usages.get().competence_id, b.usages.get().competence_id)
        self.assertEqual(a.usages.get().competence_id, retour.usages.get().competence_id)
        self.assertEqual(AdoptionReferentiel.objects.filter(classe=self.classe, courante=True).count(), 1)
        self.assertEqual(Observation.objects.count(), 0)

    def test_classe_renseignee_refusee_sans_perte(self):
        self.creer_trace(commentaire="Trace conservée")
        avant = list(Trace.objects.values())
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk)
        self.assertTrue(apercu["bloquee"])
        with self.assertRaises(ValidationError): self.adopter()
        self.assertFalse(VersionSourceEcole.objects.exists())
        self.assertEqual(list(Trace.objects.values()), avant)

    def test_permission_revision_et_adoption_perimees(self):
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk)
        self.adopter(self.b)
        with self.assertRaises(ValidationError):
            adopter_base(utilisateur=self.enseignant, classe=self.classe, version_id=self.a.pk,
                revisions_attendues=apercu["revisions"], adoption_attendue=apercu["adoption_id"])
        with self.assertRaises(PermissionDenied):
            apercu_adoption(utilisateur=get_user_model().objects.create_user(username="sans-affectation-fictif"), classe=self.classe, version_id=self.a.pk)

    def test_nouvelle_classe_n_affiche_pas_tout_catalogue(self):
        self.adopter()
        nouvelle = Classe.objects.create(ecole=self.ecole, nom="Papillons", annee_scolaire=self.classe.annee_scolaire)
        self.assertEqual(arbre_competences(self.ecole, classe=nouvelle), [])
        with self.assertRaises(PermissionDenied): usage_pour_saisie(nouvelle, self.competence)
        self.assertFalse(AdoptionReferentiel.objects.filter(classe=nouvelle).exists())

    def test_interface_jeton_et_confirmation(self):
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.get(url)
        self.assertContains(page, "Choisir le référentiel de la classe")
        self.assertFalse(VersionSourceEcole.objects.exists())
        page = self.client.post(url, {"action": "apercu", "version": self.a.pk})
        jeton = page.context["jeton"]
        self.assertTrue(jeton)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": "invalide"}).status_code, 400)
        self.assertRedirects(self.client.post(url, {"action": "confirmer", "jeton": jeton}),
                             reverse("classe_detail", args=[self.classe.pk]))
        self.assertEqual(AdoptionReferentiel.objects.get(classe=self.classe, courante=True).version_id, self.a.pk)
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": jeton}).status_code, 400)

    def test_version_non_autorisee_refusee(self):
        hors = importer(document("hors-liste"))[0]
        with self.assertRaises(ValidationError): self.adopter(hors)
        self.assertEqual(self.client.post(reverse("referentiel_classe", args=[self.classe.pk]),
            {"action": "apercu", "version": hors.pk}).status_code, 400)

    def test_cloture_definitions_et_ressources_source(self):
        adoption = self.adopter()
        competence = adoption.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="en_cours")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            finale = clore(utilisateur=self.enseignant, classe=self.classe)
            self.assertEqual(finale.etat_final["contenu"]["competences"][0]["libelle"], "Je parle")
            self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
            with self.assertRaises(ValidationError): self.adopter(self.b)

    def test_acquisition_hors_base_reste_dans_parcours_complet(self):
        self.adopter()
        # Un élève arrivé plus tard peut avoir un apprentissage d'une autre base.
        self.creer_trace(commentaire="Acquisition fictive conservée")
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Acquisition fictive conservée")
        self.assertContains(page, self.competence.libelle)

    def test_deux_versions_gardent_leurs_images_et_phrases(self):
        premiere = self.adopter()
        doc = document(version="2")
        doc["domaines"][0]["competences"][0].update(icone="livre", formulations=[{"code": "p1", "texte": "Autre proposition fidèle."}])
        deux = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk, deux.pk],
                                 proposee_id=self.a.pk, revision_attendue=1)
        autre = Classe.objects.create(ecole=self.ecole, nom="Hirondelles", annee_scolaire=self.classe.annee_scolaire)
        apercu = apercu_adoption(utilisateur=self.direction, classe=autre, version_id=deux.pk)
        adoption = adopter_base(utilisateur=self.direction, classe=autre, version_id=deux.pk,
                               revisions_attendues=apercu["revisions"], adoption_attendue=None)
        competence = adoption.usages.get().competence
        self.assertEqual(competence.pk, premiere.usages.get().competence_id)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(illustration_effective(self.ecole, competence, autre).icone, "livre")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "<prénom> prend la parole.")
        self.assertEqual(propositions(competence, autre)[0]["texte"], "Autre proposition fidèle.")
