import json

from django.test import override_settings
from django.urls import reverse

from pwa.partage_grist import empreinte
from .models import PartageGristClasse, VersionReferentiel
from . import tests_mises_a_jour_referentiels as fixtures
from .tests import Base


@override_settings(ROOT_URLCONF="pwa.urls")
class PartageGristPWA(Base):
    adopter = fixtures.MisesAJour.adopter

    def setUp(self):
        # Préparer la même source versionnée que les recettes d’adoption.
        super().setUp()
        from .tests_import_sources_referentiels import document, importer
        from .services.choix_bases_referentiels import publier_choix_application
        self.a = importer(document())[0]
        publier_choix_application(annee=self.classe.annee_scolaire, versions_ids=[self.a.pk],
                                 proposee_id=self.a.pk, revision_attendue=0)
        self.entrer()

    def test_propre_identifiant_ignore_et_confirmation_idempotente(self):
        from uuid import uuid4

        self.adopter()
        espace = reverse("espace_grist_classe", args=[self.classe.pk])
        grist = "https://grist.numerique.gouv.fr/o/docs/document-fictif"
        self.assertContains(self.client.get(espace, {"grist": grist}), grist)
        self.assertFalse(PartageGristClasse.objects.exists())
        self.assertRedirects(self.client.post(espace, {"grist": grist, "confirmer": "oui"}), espace)
        url = reverse("synchroniser_grist")
        données = self.client.get(url).json()
        travail = données["partages"][0]
        self.assertEqual(données["propres"], [travail["id"]])
        self.assertEqual(travail["empreinte"], empreinte(travail["contenu"]))
        distant = str(uuid4())
        reçu = json.loads(travail["contenu"])
        reçu["source"]["titre"] = "Référentiel du collègue"
        lignes = [{"Identifiant": travail["id"], "Contenu": "ne doit jamais être importé"},
                  {"Identifiant": distant, "Contenu": json.dumps(reçu)}]
        confirmation = {"id": travail["id"], "api": travail["api"], "lignes": lignes,
                        "nom": "Mon École partagée", "confirme": travail["empreinte"]}
        for _ in range(2):
            self.assertEqual(self.client.post(url, confirmation, content_type="application/json").json(),
                             {"erreurs": 0, "nom": "Mon École partagée"})
        self.assertEqual(VersionReferentiel.objects.filter(source__titre="Référentiel du collègue").count(), 1)
        self.assertIsNone(self.client.get(url).json()["partages"][0]["contenu"])
        self.client.post(espace, {"action": "suspendre"})
        self.assertEqual(self.client.get(url).json()["partages"], [])
        self.client.post(espace, {"grist": grist, "confirmer": "oui"})
        self.assertEqual(self.client.get(url).json()["partages"][0]["id"], travail["id"])
