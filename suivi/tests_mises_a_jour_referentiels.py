from django.core.exceptions import PermissionDenied
from django.urls import reverse

from .tests import Base
from . import tests_adoption_bases_referentiels as fixtures
from .tests_import_sources_referentiels import document, importer
from .models import Competence, EtatAnnuelObservation, Observation, VersionSourceEcole
from .services.adoption_bases_referentiels import apercu_adoption
from .services.choix_bases_referentiels import publier_choix_application
from .services.adaptations_referentiels import enregistrer_adaptation
from .services.contextes_referentiels import usage_pour_saisie
from .services.pedagogie import modifier_etat
from .referentiels import contenu_adoption


class MisesAJour(Base):
    def setUp(self):
        super().setUp()
        from .services.reprise_referentiels import reprendre
        reprendre(self.ecole.pk)
        doc = document()
        doc["domaines"][0]["competences"][0].update(icone="parler",
            formulations=[{"code": "p1", "texte": "<prénom> prend la parole."}])
        self.a = importer(doc)[0]
        self.b = importer(document("autre-fictive"))[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, self.b.pk], proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    adopter = fixtures.AdoptionBases.adopter

    def preparer(self, retirer=False, phrases=False):
        ancienne = self.adopter()
        doc = document(version="2")
        c = doc["domaines"][0]["competences"][0]
        c.update(libelle="Je prends la parole", code="L02", icone="livre")
        if phrases:
            c["formulations"] = [{"code": "p1", "texte": "<prénom> partage une découverte."}]
        if retirer:
            c["identite"] = "autre-apprentissage"
        doc["domaines"][0]["competences"].append({"identite": "ecouter", "code": "L03",
            "libelle": "J’écoute mes camarades", "niveau": "PS"})
        nouvelle = importer(doc)[0]
        publier_choix_application(annee=self.classe.annee_scolaire,
            versions_ids=[self.a.pk, nouvelle.pk], proposee_id=nouvelle.pk, revision_attendue=1)
        return ancienne, nouvelle

    def adapter(self, ancienne, classe=True, texte="Mon texte fictif"):
        return enregistrer_adaptation(utilisateur=self.enseignant if classe else self.direction,
            ecole=self.ecole, annee=self.classe.annee_scolaire,
            competence=ancienne.usages.get().competence, classe=self.classe if classe else None,
            adoption_attendue=ancienne.pk if classe else None,
            revision_attendue=0, libelle=texte, visible=False if classe else None)

    def test_apercu_sans_projection_et_adaptation_prioritaire(self):
        ancienne, nouvelle = self.preparer()
        self.adapter(ancienne, classe=False, texte="Proposition école fictive")
        self.adapter(ancienne)
        nombre = Competence.objects.count()
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=nouvelle.pk)
        self.assertEqual(Competence.objects.count(), nombre)
        self.assertFalse(VersionSourceEcole.objects.filter(version=nouvelle).exists())
        detail = apercu["mise_a_jour"]
        self.assertEqual(detail["modifiees"][0]["avant"], "Je parle")
        self.assertIn("Phrases proposées", detail["modifiees"][0]["changements"])
        self.assertEqual(detail["ajoutees"], ["J’écoute mes camarades"])
        self.assertEqual(detail["retirees"], [])
        self.assertEqual(detail["adaptations"][0]["libelle"], "Mon texte fictif")
        self.assertFalse(detail["adaptations"][0]["visible"])
        adoption = self.adopter(nouvelle)
        self.assertEqual(ancienne.usages.get().competence_id,
            next(c["id"] for c in adoption.contenu["competences"] if c["code"] == "L02"))
        effective = next(c for c in contenu_adoption(adoption)["competences"] if c["code"] == "L02")
        self.assertEqual(effective["libelle"], "Mon texte fictif")
        self.assertFalse(effective["active"])

    def test_retrait_et_nouveau_sens_conservent_ancien_etat(self):
        ancienne, nouvelle = self.preparer(retirer=True)
        competence = ancienne.usages.get().competence
        modifier_etat(utilisateur=self.enseignant, eleve=self.eleve, competence=competence, statut="reussi")
        etats = list(EtatAnnuelObservation.objects.values())
        observations = list(Observation.objects.values())
        apercu = apercu_adoption(utilisateur=self.enseignant, classe=self.classe, version_id=nouvelle.pk)
        self.assertEqual(apercu["mise_a_jour"]["retirees"], ["Je parle"])
        self.adopter(nouvelle)
        self.assertEqual(list(EtatAnnuelObservation.objects.values()), etats)
        self.assertEqual(list(Observation.objects.values()), observations)
        with self.assertRaises(PermissionDenied):
            usage_pour_saisie(self.classe, competence)
        page = self.client.get(reverse("carnet", args=[self.eleve.pk]), {"contenu": "tout"})
        self.assertContains(page, "Je parle")
        self.adopter(self.a)
        self.assertEqual(self.classe._adoption_referentiel_lecture.usages.get().competence_id, competence.pk)

    def test_confirmation_refuse_adaptation_changee(self):
        ancienne, nouvelle = self.preparer()
        url = reverse("referentiel_classe", args=[self.classe.pk])
        page = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertContains(page, "Adopter cette version pour la classe")
        jeton = page.context["jeton"]
        self.adapter(ancienne)
        page = self.client.post(url, {"action": "confirmer", "jeton": jeton})
        self.assertEqual(page.status_code, 400)
        self.assertContains(page, "Les adaptations ont changé", status_code=400)
        self.assertFalse(VersionSourceEcole.objects.filter(version=nouvelle).exists())
        page = self.client.post(url, {"action": "apercu", "version": nouvelle.pk})
        self.assertEqual(self.client.post(url, {"action": "confirmer", "jeton": page.context["jeton"]}).status_code, 302)

    def test_autre_source_et_meme_version_ne_sont_pas_mises_a_jour(self):
        self.adopter()
        for version in (self.a, self.b):
            self.assertIsNone(apercu_adoption(utilisateur=self.enseignant,
                classe=self.classe, version_id=version.pk)["mise_a_jour"])

    def test_propositions_suivent_version_et_choix_personnels_restent(self):
        from .models import ReglagePresentation
        from .presentation import illustration_effective, propositions
        from .services.presentation import enregistrer_formulation, enregistrer_reglage
        ancienne, nouvelle = self.preparer(phrases=True)
        competence = ancienne.usages.get().competence
        cle = propositions(competence, self.classe)[0]["cle"]
        enregistrer_formulation(utilisateur=self.enseignant, competence=competence,
            classe=self.classe, cle=cle, texte="Ma phrase fictive conservée")
        enregistrer_reglage(self.enseignant, ReglagePresentation(ecole=self.ecole,
            classe=self.classe, competence=competence, mode="remplacer", icone="parler"))
        self.adopter(nouvelle)
        self.assertEqual(illustration_effective(self.ecole, competence, self.classe).icone, "parler")
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "Ma phrase fictive conservée")
        self.assertEqual(ancienne.contenu["formulations"][0]["texte"], "<prénom> prend la parole.")

    def test_phrase_retiree_conserve_adaptation_pour_retour(self):
        from .models import FormulationLocale
        from .presentation import propositions
        from .services.presentation import enregistrer_formulation
        ancienne, nouvelle = self.preparer()
        competence = ancienne.usages.get().competence
        enregistrer_formulation(utilisateur=self.enseignant, competence=competence,
            classe=self.classe, cle=propositions(competence, self.classe)[0]["cle"],
            texte="Ma phrase adaptée fictive")
        self.adopter(nouvelle)
        self.assertEqual(propositions(competence, self.classe), [])
        self.assertEqual(FormulationLocale.objects.get().texte, "Ma phrase adaptée fictive")
        self.adopter(self.a)
        self.assertEqual(propositions(competence, self.classe)[0]["texte"], "Ma phrase adaptée fictive")
